from __future__ import annotations
import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.providers.torrents.qbittorrent import QBittorrentProvider


class TorrentWatcher:
    """Polls qBittorrent every 30s and emits TorrentCompleted events for finished torrents."""

    def __init__(self, provider: "QBittorrentProvider", poll_interval: int = 30):
        self._provider = provider
        self._interval = poll_interval
        self._monitored: dict[str, dict] = {}  # hash → {anime_id, episode}
        self._running = False
        self._task: asyncio.Task | None = None

    def track(self, torrent_hash: str, anime_id: int, episode: int) -> None:
        self._monitored[torrent_hash.lower()] = {"anime_id": anime_id, "episode": episode}

    def untrack(self, torrent_hash: str) -> None:
        self._monitored.pop(torrent_hash.lower(), None)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.get_event_loop().create_task(self._loop())

    def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None

    async def _loop(self) -> None:
        from app.core.events.bus import bus, TorrentCompleted

        while self._running:
            try:
                if self._monitored:
                    completed = await self._provider.get_completed()
                    done_hashes = {t["hash"].lower() for t in completed}
                    for torrent_hash in list(self._monitored.keys()):
                        if torrent_hash in done_hashes:
                            entry = next((t for t in completed if t["hash"].lower() == torrent_hash), {})
                            await bus.publish(TorrentCompleted(
                                torrent_hash=torrent_hash,
                                save_path=entry.get("save_path", ""),
                                name=entry.get("name", ""),
                            ))
                            self.untrack(torrent_hash)
            except Exception as e:
                print(f"[TorrentWatcher] erro: {e}")
            await asyncio.sleep(self._interval)
