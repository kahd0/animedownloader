from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Release:
    title: str
    normalized_title: str
    episode: int | None
    season: int
    resolution: str          # "1080p", "720p", "480p"
    source: str              # "SubsPlease", "Erai", "generic"
    magnet: str
    torrent_hash: str | None = None
    release_group: str | None = None
    language: str = "raw"    # "pt-br", "en", "raw"
    published_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    score: int = 0
    crc: str | None = None

    def __str__(self) -> str:
        ep = f"E{self.episode:02d}" if self.episode is not None else "?"
        return f"[{self.source}] {self.normalized_title} {ep} [{self.resolution}]"
