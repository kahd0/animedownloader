from __future__ import annotations
import asyncio
from typing import Callable


class AppState:
    """Centralized reactive state for the UI layer.

    Subscribes to the event bus and triggers UI callbacks on state changes.
    All callbacks are called from the background async loop and should
    schedule UI updates via app.after() if touching tkinter widgets.
    """

    def __init__(self):
        self._refresh_callbacks: list[Callable] = []
        self._log_callbacks: list[Callable[[str, str], None]] = []
        self._setup_bus_subscriptions()

    def on_refresh(self, callback: Callable) -> None:
        """Register a callback to be called when anime data should be reloaded."""
        self._refresh_callbacks.append(callback)

    def on_log(self, callback: Callable[[str, str], None]) -> None:
        """Register a callback(message, color) for log messages from the pipeline."""
        self._log_callbacks.append(callback)

    def _setup_bus_subscriptions(self) -> None:
        from app.core.events.bus import bus
        from app.core.events.bus import (
            EpisodeDetected,
            TorrentAdded,
            TorrentCompleted,
            SubtitleFound,
            SubtitleTranslated,
            MediaOrganized,
            EpisodeReady,
            PipelineFailed,
        )

        bus.subscribe(EpisodeDetected, self._on_episode_detected)
        bus.subscribe(TorrentAdded, self._on_torrent_added)
        bus.subscribe(TorrentCompleted, self._on_torrent_completed)
        bus.subscribe(SubtitleFound, self._on_subtitle_found)
        bus.subscribe(SubtitleTranslated, self._on_subtitle_translated)
        bus.subscribe(MediaOrganized, self._on_media_organized)
        bus.subscribe(EpisodeReady, self._on_episode_ready)
        bus.subscribe(PipelineFailed, self._on_pipeline_failed)

    async def _on_episode_detected(self, event) -> None:
        self._log(f"Novo episódio detectado: {event.title_pattern} EP{event.episode:02d}", "cyan")

    async def _on_torrent_added(self, event) -> None:
        self._log(f"Torrent adicionado — EP{event.episode:02d} [{event.torrent_hash[:8]}...]", "blue")

    async def _on_torrent_completed(self, event) -> None:
        self._log(f"Download concluído: {event.name}", "green")

    async def _on_subtitle_found(self, event) -> None:
        lang = event.language.upper()
        self._log(f"Legenda encontrada [{lang}] — EP{event.episode:02d}", "green")

    async def _on_subtitle_translated(self, event) -> None:
        self._log(f"Legenda traduzida — EP{event.episode:02d}", "green")

    async def _on_media_organized(self, event) -> None:
        import os
        self._log(f"Organizado: {os.path.basename(event.final_path)}", "green")

    async def _on_episode_ready(self, event) -> None:
        self._log(f"✓ EP{event.episode:02d} pronto — {event.title_pattern}", "green")
        self._trigger_refresh()

    async def _on_pipeline_failed(self, event) -> None:
        self._log(f"[ERRO] {event.step} — EP{event.episode:02d}: {event.error}", "red")

    def _log(self, message: str, color: str = "white") -> None:
        for cb in self._log_callbacks:
            try:
                cb(message, color)
            except Exception:
                pass

    def _trigger_refresh(self) -> None:
        for cb in self._refresh_callbacks:
            try:
                cb()
            except Exception:
                pass


# Global singleton
app_state = AppState()
