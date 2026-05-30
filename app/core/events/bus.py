from __future__ import annotations
import asyncio
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable, Coroutine, Type


@dataclass
class BaseEvent:
    pass


@dataclass
class EpisodeDetected(BaseEvent):
    anime_id: int
    title_pattern: str
    episode: int
    magnet: str
    resolution: str
    source: str


@dataclass
class TorrentAdded(BaseEvent):
    anime_id: int
    episode: int
    torrent_hash: str


@dataclass
class TorrentCompleted(BaseEvent):
    torrent_hash: str
    save_path: str
    name: str


@dataclass
class FileDetected(BaseEvent):
    path: str


@dataclass
class SubtitleFound(BaseEvent):
    anime_id: int
    episode: int
    path: str
    language: str
    provider: str


@dataclass
class SubtitleTranslated(BaseEvent):
    anime_id: int
    episode: int
    path: str


@dataclass
class MediaOrganized(BaseEvent):
    anime_id: int
    episode: int
    final_path: str


@dataclass
class EpisodeReady(BaseEvent):
    anime_id: int
    episode: int
    title_pattern: str


@dataclass
class PipelineFailed(BaseEvent):
    anime_id: int
    episode: int
    step: str
    error: str


@dataclass
class Notify(BaseEvent):
    """User-facing notification surfaced as a toast by the UI layer."""
    level: str   # "info" | "success" | "warning" | "error"
    message: str


Handler = Callable[[BaseEvent], Coroutine[Any, Any, None]]


class EventBus:
    """Simple in-process async event bus."""

    def __init__(self):
        self._handlers: dict[type, list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: Type[BaseEvent], handler: Handler) -> None:
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: Type[BaseEvent], handler: Handler) -> None:
        self._handlers[event_type] = [h for h in self._handlers[event_type] if h is not handler]

    async def publish(self, event: BaseEvent) -> None:
        handlers = self._handlers.get(type(event), [])
        if handlers:
            await asyncio.gather(*[h(event) for h in handlers], return_exceptions=True)

    def publish_sync(self, event: BaseEvent) -> None:
        """Fire-and-forget from sync context — schedules in the running event loop."""
        try:
            loop = asyncio.get_event_loop()
            loop.create_task(self.publish(event))
        except RuntimeError:
            pass


# Global singleton
bus = EventBus()
