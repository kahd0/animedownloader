from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class SubtitleResult:
    provider: str
    language: str            # "pt-br", "en", "ja"
    filename: str
    download_url: str | None = None
    raw_bytes: bytes | None = None
    score: int = 0
    format: str = "ass"      # "ass", "srt", "sub"
    release_group: str | None = None
    episode: int | None = None

    @property
    def is_portuguese(self) -> bool:
        return self.language.lower() in ("pt-br", "pt", "portuguese")

    @property
    def ext(self) -> str:
        return f".{self.format}"
