from __future__ import annotations
import os

from app.core import database as db
from app.models.subtitle import SubtitleResult
from app.services.release_scorer import rank_subtitles


class SubtitleService:
    """Finds and downloads the best subtitle using a configurable fallback chain."""

    def __init__(self):
        self._providers = self._build_providers()

    def _build_providers(self):
        from app.core.config import get_setting, get_subtitle_sources
        from app.providers.subtitles.opensubtitles import OpenSubtitlesProvider
        from app.providers.subtitles.jimaku import JimakuProvider

        providers_map = {
            "opensubtitles": OpenSubtitlesProvider(get_setting("opensubtitles_api_key", "")),
            "jimaku": JimakuProvider(),
        }

        ordered = []
        for source in get_subtitle_sources():
            if source.get("enabled") and source["id"] in providers_map:
                ordered.append(providers_map[source["id"]])

        if not ordered:
            ordered = [providers_map["opensubtitles"]]

        return ordered

    async def search(self, title: str, episode: int) -> list[SubtitleResult]:
        """Search all providers and return ranked results."""
        all_results: list[SubtitleResult] = []
        has_ptbr = False

        for provider in self._providers:
            try:
                results = await provider.search(title, episode)
                all_results.extend(results)
                if any(r.is_portuguese for r in results):
                    has_ptbr = True
                    # Don't skip remaining providers — still collect for scoring
            except Exception as e:
                print(f"[SubtitleService] {provider.name} search erro: {e}")

        return rank_subtitles(all_results)

    async def download(self, result: SubtitleResult, dest_path: str) -> str:
        """Download a subtitle result and write to dest_path."""
        provider = next((p for p in self._providers if p.name == result.provider), None)
        if not provider:
            raise ValueError(f"Provider {result.provider} não encontrado")

        content = await provider.download(result)
        os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(content)
        return dest_path

    async def find_and_download(
        self,
        anime_id: int,
        title: str,
        episode: int,
        video_dir: str = "",
        video_path: str = "",
    ) -> str | None:
        """Find best subtitle, check cache, download, and return local path."""
        # Check cache first
        for lang in ("pt-br", "en"):
            cached = await db.get_cached_subtitle(anime_id, episode, lang)
            if cached and cached.get("filename") and os.path.exists(cached["filename"]):
                return cached["filename"]

        results = await self.search(title, episode)
        if not results:
            return None

        best = results[0]
        ext = best.ext
        if video_path:
            stem = os.path.splitext(os.path.basename(video_path))[0]
            dest = os.path.join(os.path.dirname(video_path), f"{stem}{ext}")
        elif video_dir:
            safe = _safe_name(title)
            dest = os.path.join(video_dir, f"{safe}_ep{episode:02d}{ext}")
        else:
            from app.core.config import get_subs_dir
            safe = _safe_name(title)
            dest = os.path.join(get_subs_dir(), f"{safe}_ep{episode:02d}{ext}")

        try:
            path = await self.download(best, dest)
            import hashlib
            with open(path, "rb") as _f:
                file_hash = hashlib.md5(_f.read()).hexdigest()
            await db.save_subtitle_cache(anime_id, episode, best.provider, best.language, path, file_hash)
            return path
        except Exception as e:
            print(f"[SubtitleService] download erro: {e}")
            return None


def _safe_name(title: str) -> str:
    import re
    return re.sub(r"[^\w\s-]", "", title).strip().lower().replace(" ", "_")
