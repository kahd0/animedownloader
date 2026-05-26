from __future__ import annotations
from app.models.subtitle import SubtitleResult
from app.providers.base import SubtitleProvider


class JimakuProvider(SubtitleProvider):
    """Jimaku subtitle provider — stub for future implementation."""

    name = "jimaku"
    priority = 40

    async def search(self, title: str, episode: int) -> list[SubtitleResult]:
        return []

    async def download(self, result: SubtitleResult) -> bytes:
        raise NotImplementedError("Jimaku provider not yet implemented")
