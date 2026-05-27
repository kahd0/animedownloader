from __future__ import annotations
import asyncio
import os
from typing import Any

from app.core.events.bus import (
    bus,
    EpisodeDetected,
    TorrentAdded,
    TorrentCompleted,
    FileDetected,
    SubtitleFound,
    SubtitleTranslated,
    MediaOrganized,
    EpisodeReady,
    PipelineFailed,
)
from app.core.jobs.queue import job_queue
from app.core import database as db
from app.core.config import get_setting, get_source_dir, get_final_dir


class EpisodePipeline:
    """
    Orchestrates the full episode lifecycle:
    EpisodeDetected → TorrentAdded → TorrentCompleted →
    SubtitleFound → SubtitleTranslated → MediaOrganized → EpisodeReady
    """

    def __init__(self):
        self._qbittorrent = None
        self._watcher = None
        self._fallback_pending: dict[str, dict] = {}  # "anime_id:episode" → {anime_id, episode, title_pattern}

    def setup(self, qbittorrent_provider=None, watcher=None) -> None:
        self._qbittorrent = qbittorrent_provider
        self._watcher = watcher

        bus.subscribe(EpisodeDetected, self._on_episode_detected)
        bus.subscribe(TorrentCompleted, self._on_torrent_completed)
        bus.subscribe(FileDetected, self._on_file_detected)

        job_queue.register("subtitle", self._job_subtitle)
        job_queue.register("translation", self._job_translation)
        job_queue.register("organization", self._job_organization)

    async def _on_episode_detected(self, event: EpisodeDetected) -> None:
        """Handle a newly detected episode: add to qBittorrent or fallback to xdg-open."""
        try:
            if self._qbittorrent and await self._qbittorrent.is_available():
                torrent_hash = await self._qbittorrent.add_magnet(event.magnet)
                await db.save_release(
                    anime_id=event.anime_id,
                    episode=event.episode,
                    title=event.title_pattern,
                    magnet=event.magnet,
                    torrent_hash=torrent_hash,
                    resolution=event.resolution,
                    source=event.source,
                )
                if self._watcher and torrent_hash:
                    self._watcher.track(torrent_hash, event.anime_id, event.episode)
                await bus.publish(TorrentAdded(
                    anime_id=event.anime_id,
                    episode=event.episode,
                    torrent_hash=torrent_hash,
                ))
            else:
                _open_magnet(event.magnet)
                await db.save_release(
                    anime_id=event.anime_id,
                    episode=event.episode,
                    title=event.title_pattern,
                    magnet=event.magnet,
                    torrent_hash=None,
                    resolution=event.resolution,
                    source=event.source,
                )
                # Register for filesystem detection: FilesystemWatcher will emit
                # FileDetected when the video file lands on disk, triggering the pipeline.
                key = f"{event.anime_id}:{event.episode}"
                self._fallback_pending[key] = {
                    "anime_id": event.anime_id,
                    "episode": event.episode,
                    "title_pattern": event.title_pattern,
                }
        except Exception as e:
            await bus.publish(PipelineFailed(
                anime_id=event.anime_id,
                episode=event.episode,
                step="download",
                error=str(e),
            ))

    async def _on_torrent_completed(self, event: TorrentCompleted) -> None:
        """When a torrent finishes, enqueue subtitle search."""
        # Find which anime/episode owns this hash
        row = await _find_release_by_hash(event.torrent_hash)
        if not row:
            return
        anime_id, episode = row
        await job_queue.enqueue(
            "subtitle",
            anime_id=anime_id,
            episode=episode,
            save_path=event.save_path,
            name=event.name,
        )

    async def _on_file_detected(self, event: FileDetected) -> None:
        """Handle a video file detected by FilesystemWatcher (xdg-open fallback path)."""
        if not self._fallback_pending:
            return
        filename = os.path.basename(event.path).lower()
        for key, entry in list(self._fallback_pending.items()):
            if entry["title_pattern"].lower() in filename:
                del self._fallback_pending[key]
                await job_queue.enqueue(
                    "subtitle",
                    anime_id=entry["anime_id"],
                    episode=entry["episode"],
                    save_path=os.path.dirname(event.path),
                    name=os.path.basename(event.path),
                )
                break

    async def _job_subtitle(self, payload: dict[str, Any]) -> None:
        """Job: find and download best subtitle."""
        anime_id = payload["anime_id"]
        episode = payload["episode"]
        save_path = payload.get("save_path", "")

        from app.services.subtitle_service import SubtitleService
        service = SubtitleService()

        # Get anime title pattern
        animes = await db.get_monitored_animes()
        anime = next((a for a in animes if a[0] == anime_id), None)
        if not anime:
            raise ValueError(f"Anime {anime_id} não encontrado")
        title_pattern = anime[1]

        subtitle_path = await service.find_and_download(
            anime_id=anime_id,
            title=title_pattern,
            episode=episode,
            video_dir=save_path,
        )

        if subtitle_path:
            await bus.publish(SubtitleFound(
                anime_id=anime_id,
                episode=episode,
                path=subtitle_path,
                language=_detect_language(subtitle_path),
                provider="auto",
            ))
            if not _detect_language(subtitle_path).startswith("pt"):
                # Bug 2 fix: pass video_dir so _job_translation can forward it to organization
                await job_queue.enqueue(
                    "translation",
                    anime_id=anime_id,
                    episode=episode,
                    subtitle_path=subtitle_path,
                    video_dir=save_path,
                )
            else:
                await job_queue.enqueue(
                    "organization",
                    anime_id=anime_id,
                    episode=episode,
                    video_dir=save_path,
                )
        else:
            # Bug 1 fix: no subtitle found — still organize so episode isn't stuck
            await job_queue.enqueue(
                "organization",
                anime_id=anime_id,
                episode=episode,
                video_dir=save_path,
            )

    async def _job_translation(self, payload: dict[str, Any]) -> None:
        """Job: translate subtitle to PT-BR."""
        anime_id = payload["anime_id"]
        episode = payload["episode"]
        subtitle_path = payload.get("subtitle_path", "")
        # Bug 3 fix: forward video_dir that was passed from _job_subtitle
        video_dir = payload.get("video_dir", "")

        from app.services.translation_service import TranslationService
        service = TranslationService()

        translated_path = subtitle_path  # fallback to original if translation fails
        try:
            translated_path = await service.translate(subtitle_path, anime_id=anime_id)
            await bus.publish(SubtitleTranslated(
                anime_id=anime_id,
                episode=episode,
                path=translated_path,
            ))
        except Exception as e:
            # Bug 4 fix: report failure but always fall through to organization
            await bus.publish(PipelineFailed(
                anime_id=anime_id,
                episode=episode,
                step="translation",
                error=str(e),
            ))
        finally:
            await job_queue.enqueue(
                "organization",
                anime_id=anime_id,
                episode=episode,
                subtitle_path=translated_path,
                video_dir=video_dir,
            )

    async def _job_organization(self, payload: dict[str, Any]) -> None:
        """Job: organize video file into final directory."""
        anime_id = payload["anime_id"]
        episode = payload["episode"]
        video_dir = payload.get("video_dir", get_source_dir())

        from app.services.media_organizer import MediaOrganizer
        organizer = MediaOrganizer()

        animes = await db.get_monitored_animes()
        anime = next((a for a in animes if a[0] == anime_id), None)
        if not anime:
            return
        title_pattern, official_title = anime[1], anime[6]
        display_title = official_title or title_pattern

        final_path = await organizer.organize(
            title=display_title,
            episode=episode,
            source_dir=video_dir,
            dest_dir=get_final_dir(),
        )
        if final_path:
            await db.mark_episode_ready(title_pattern, episode)

            # Remove torrent from qBittorrent now that the file is organized
            if self._qbittorrent:
                torrent_hash = await _find_hash_for_episode(anime_id, episode)
                if torrent_hash:
                    try:
                        await self._qbittorrent.remove_torrent(torrent_hash)
                    except Exception as e:
                        print(f"[Pipeline] remove_torrent erro: {e}")

            await bus.publish(MediaOrganized(
                anime_id=anime_id,
                episode=episode,
                final_path=final_path,
            ))
            await bus.publish(EpisodeReady(
                anime_id=anime_id,
                episode=episode,
                title_pattern=title_pattern,
            ))


async def _find_hash_for_episode(anime_id: int, episode: int) -> str | None:
    """Return the torrent_hash stored for a given anime_id+episode, or None."""
    from app.core.config import DB_PATH
    import aiosqlite
    async with aiosqlite.connect(DB_PATH) as db_conn:
        async with db_conn.execute(
            "SELECT torrent_hash FROM releases WHERE anime_id = ? AND episode = ? LIMIT 1",
            (anime_id, episode),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row and row[0] else None


async def _find_release_by_hash(torrent_hash: str) -> tuple[int, int] | None:
    """Find (anime_id, episode) for a torrent hash."""
    from app.core.config import DB_PATH
    import aiosqlite
    async with aiosqlite.connect(DB_PATH) as db_conn:
        async with db_conn.execute(
            "SELECT anime_id, episode FROM releases WHERE torrent_hash = ? LIMIT 1",
            (torrent_hash,),
        ) as cursor:
            row = await cursor.fetchone()
            return (row[0], row[1]) if row else None


def _detect_language(path: str) -> str:
    p = path.lower()
    if any(t in p for t in ("pt-br", "ptbr", "portuguese", "brasil")):
        return "pt-br"
    try:
        import re as _re
        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            sample = f.read(8192)
        # Hiragana, Katakana, CJK Unified Ideographs
        if _re.search(r"[぀-ゟ゠-ヿ一-鿿]", sample):
            return "ja"
        if any(t in sample.lower() for t in ("pt-br", "portuguese", "brasil")):
            return "pt-br"
    except Exception:
        pass
    return "en"


def _open_magnet(magnet: str) -> None:
    import platform
    import subprocess
    import webbrowser
    system = platform.system().lower()
    try:
        if system == "linux":
            subprocess.Popen(["xdg-open", magnet])
        elif system == "darwin":
            subprocess.Popen(["open", magnet])
        else:
            webbrowser.open(magnet)
    except Exception as e:
        print(f"[Pipeline] open magnet erro: {e}")


# Global singleton
pipeline = EpisodePipeline()
