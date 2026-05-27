from __future__ import annotations
import asyncio
from typing import Any

from app.providers.base import TorrentProvider


class QBittorrentProvider(TorrentProvider):
    """qBittorrent Web API provider using qbittorrent-api library."""

    name = "qbittorrent"

    def __init__(self, host: str = "localhost", port: int = 8080, username: str = "", password: str = ""):
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._client: Any = None

    def _get_client(self) -> Any:
        try:
            import qbittorrentapi
        except ImportError:
            raise ImportError("qbittorrent-api is not installed. Run: pip install qbittorrent-api")

        if self._client is None:
            self._client = qbittorrentapi.Client(
                host=self._host,
                port=self._port,
                username=self._username,
                password=self._password,
            )
            self._client.auth_log_in()
        return self._client

    async def is_available(self) -> bool:
        try:
            client = await asyncio.to_thread(self._get_client)
            await asyncio.to_thread(client.app_version)
            return True
        except Exception:
            return False

    async def add_magnet(self, magnet: str, save_path: str | None = None) -> str:
        def _add():
            client = self._get_client()
            kwargs: dict[str, Any] = {"urls": magnet}
            if save_path:
                kwargs["save_path"] = save_path
            client.torrents_add(**kwargs)
            # Retrieve hash from the magnet URI
            for part in magnet.split("&"):
                if part.startswith("xt=urn:btih:"):
                    return part.split(":")[-1].lower()
            return ""

        return await asyncio.to_thread(_add)

    async def get_status(self, torrent_hash: str) -> dict[str, Any]:
        def _status():
            client = self._get_client()
            torrents = client.torrents_info(torrent_hashes=torrent_hash)
            if not torrents:
                return {"state": "unknown", "progress": 0.0}
            t = torrents[0]
            return {
                "state": t.state,
                "progress": t.progress,
                "name": t.name,
                "save_path": t.save_path,
                "size": t.size,
                "hash": t.hash,
            }

        return await asyncio.to_thread(_status)

    async def get_completed(self) -> list[dict[str, Any]]:
        def _completed():
            client = self._get_client()
            torrents = client.torrents_info()
            done_states = {"seeding", "stalledUP", "pausedUP", "uploading", "queuedUP", "forcedUP"}
            return [
                {"hash": t.hash, "save_path": t.save_path, "name": t.name}
                for t in torrents
                if t.state in done_states
            ]

        return await asyncio.to_thread(_completed)

    async def remove_torrent(self, torrent_hash: str, delete_files: bool = False) -> None:
        def _remove():
            client = self._get_client()
            client.torrents_delete(delete_files=delete_files, torrent_hashes=torrent_hash)

        await asyncio.to_thread(_remove)

    async def get_all_torrents(self) -> list[dict[str, Any]]:
        """Return all torrents with full status info for the Downloads screen."""
        def _all():
            client = self._get_client()
            torrents = client.torrents_info()
            return [
                {
                    "hash":       t.hash,
                    "name":       t.name,
                    "state":      t.state,
                    "progress":   t.progress,
                    "dlspeed":    t.dlspeed,
                    "upspeed":    t.upspeed,
                    "eta":        t.eta,
                    "total_size": t.total_size,
                    "save_path":  t.save_path,
                }
                for t in torrents
            ]

        return await asyncio.to_thread(_all)
