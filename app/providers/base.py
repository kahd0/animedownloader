from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any

from app.models.release import Release
from app.models.subtitle import SubtitleResult


class RSSProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def fetch_releases(self, show_name: str) -> list[Release]:
        """Fetch releases for a given show name."""
        ...

    async def fetch_all_latest(self) -> list[Release]:
        """Fetch all currently airing releases (not all providers support this)."""
        return []


class SubtitleProvider(ABC):
    name: str = "base"
    priority: int = 50

    @abstractmethod
    async def search(self, title: str, episode: int) -> list[SubtitleResult]:
        """Search for subtitles. Returns ranked list."""
        ...

    @abstractmethod
    async def download(self, result: SubtitleResult) -> bytes:
        """Download subtitle content as bytes."""
        ...


class TranslatorProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def translate_batch(
        self,
        texts: list[str],
        source_lang: str = "ja",
        target_lang: str = "pt",
    ) -> list[str]:
        """Translate a batch of texts. Returns same-length list."""
        ...


class TorrentProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def add_magnet(self, magnet: str, save_path: str | None = None) -> str:
        """Add a magnet link. Returns torrent hash."""
        ...

    @abstractmethod
    async def get_status(self, torrent_hash: str) -> dict[str, Any]:
        """Get torrent status dict (progress, state, name, save_path)."""
        ...

    @abstractmethod
    async def get_completed(self) -> list[dict[str, Any]]:
        """Return list of completed torrents as dicts with hash and save_path."""
        ...

    async def is_available(self) -> bool:
        """Check if the provider is reachable."""
        return True


class MetadataProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def fetch_metadata(self, title: str) -> dict[str, Any] | None:
        """Fetch anime metadata. Returns dict with title, cover_url, status."""
        ...
