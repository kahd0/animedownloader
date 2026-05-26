"""Qt Signal bridge over the existing AppState event subscriptions."""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Qt
from app.utils.async_bridge import _get_bridge


class QtAppState(QObject):
    """Exposes all pipeline events as Qt Signals (thread-safe via QueuedConnection)."""

    episode_detected    = Signal(int, int, str)       # anime_id, episode, source
    torrent_added       = Signal(int, int, str)        # anime_id, episode, hash
    torrent_completed   = Signal(str, str)             # hash, name
    subtitle_found      = Signal(int, int, str, str)   # anime_id, episode, language, provider
    subtitle_translated = Signal(int, int)             # anime_id, episode
    media_organized     = Signal(int, int, str)        # anime_id, episode, path
    episode_ready       = Signal(int, int, str)        # anime_id, episode, title
    pipeline_failed     = Signal(int, int, str, str)   # anime_id, episode, step, error
    log_message         = Signal(str, str)             # message, color

    def __init__(self):
        super().__init__()
        self._setup_subscriptions()

    def _setup_subscriptions(self) -> None:
        from app.core.events.bus import bus
        from app.core.events.bus import (
            EpisodeDetected, TorrentAdded, TorrentCompleted,
            SubtitleFound, SubtitleTranslated, MediaOrganized,
            EpisodeReady, PipelineFailed,
        )

        bus.subscribe(EpisodeDetected,    self._on_episode_detected)
        bus.subscribe(TorrentAdded,       self._on_torrent_added)
        bus.subscribe(TorrentCompleted,   self._on_torrent_completed)
        bus.subscribe(SubtitleFound,      self._on_subtitle_found)
        bus.subscribe(SubtitleTranslated, self._on_subtitle_translated)
        bus.subscribe(MediaOrganized,     self._on_media_organized)
        bus.subscribe(EpisodeReady,       self._on_episode_ready)
        bus.subscribe(PipelineFailed,     self._on_pipeline_failed)

        # Also hook into AppState log callbacks
        from app.ui.state.app_state import app_state
        app_state.on_log(self._on_log)

    # ── Event handlers (called from async loop thread) ─────────────────────

    async def _on_episode_detected(self, event) -> None:
        _get_bridge()._callback_ready.emit(
            lambda _: self.episode_detected.emit(event.anime_id, event.episode, event.source),
            None,
        )

    async def _on_torrent_added(self, event) -> None:
        _get_bridge()._callback_ready.emit(
            lambda _: self.torrent_added.emit(event.anime_id, event.episode, event.torrent_hash),
            None,
        )

    async def _on_torrent_completed(self, event) -> None:
        _get_bridge()._callback_ready.emit(
            lambda _: self.torrent_completed.emit(event.torrent_hash, event.name),
            None,
        )

    async def _on_subtitle_found(self, event) -> None:
        _get_bridge()._callback_ready.emit(
            lambda _: self.subtitle_found.emit(event.anime_id, event.episode, event.language, event.provider),
            None,
        )

    async def _on_subtitle_translated(self, event) -> None:
        _get_bridge()._callback_ready.emit(
            lambda _: self.subtitle_translated.emit(event.anime_id, event.episode),
            None,
        )

    async def _on_media_organized(self, event) -> None:
        _get_bridge()._callback_ready.emit(
            lambda _: self.media_organized.emit(event.anime_id, event.episode, event.final_path),
            None,
        )

    async def _on_episode_ready(self, event) -> None:
        _get_bridge()._callback_ready.emit(
            lambda _: self.episode_ready.emit(event.anime_id, event.episode, event.title_pattern),
            None,
        )

    async def _on_pipeline_failed(self, event) -> None:
        _get_bridge()._callback_ready.emit(
            lambda _: self.pipeline_failed.emit(event.anime_id, event.episode, event.step, event.error),
            None,
        )

    def _on_log(self, message: str, color: str) -> None:
        _get_bridge()._callback_ready.emit(
            lambda _: self.log_message.emit(message, color),
            None,
        )


# Global singleton — instantiated once at app startup
qt_app_state: QtAppState | None = None


def init_qt_app_state() -> QtAppState:
    global qt_app_state
    qt_app_state = QtAppState()
    return qt_app_state
