from __future__ import annotations
from typing import Any

from app.providers.base import MetadataProvider


class AniListProvider(MetadataProvider):
    """AniList metadata provider — stub for future implementation."""

    name = "anilist"

    async def fetch_metadata(self, title: str) -> dict[str, Any] | None:
        return None
