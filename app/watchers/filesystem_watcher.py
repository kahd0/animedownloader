from __future__ import annotations
import asyncio
import os
from pathlib import Path


class FilesystemWatcher:
    """Watches a directory for new video files using watchdog."""

    VIDEO_EXTS = {".mkv", ".mp4", ".avi", ".mov", ".m4v"}

    def __init__(self, watch_path: str, poll_interval: float = 2.0):
        self._path = watch_path
        self._poll_interval = poll_interval
        self._observer = None
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._running = False
        self._loop: asyncio.AbstractEventLoop | None = None

    def start(self) -> None:
        if self._running:
            return
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler

            watcher = self

            class _Handler(FileSystemEventHandler):
                def on_created(self, event):
                    if event.is_directory:
                        return
                    ext = Path(event.src_path).suffix.lower()
                    if ext in FilesystemWatcher.VIDEO_EXTS:
                        watcher._enqueue(event.src_path)

                def on_moved(self, event):
                    if event.is_directory:
                        return
                    ext = Path(event.dest_path).suffix.lower()
                    if ext in FilesystemWatcher.VIDEO_EXTS:
                        watcher._enqueue(event.dest_path)

            os.makedirs(self._path, exist_ok=True)
            self._loop = asyncio.get_event_loop()
            self._observer = Observer()
            self._observer.schedule(_Handler(), self._path, recursive=False)
            self._observer.start()
            self._running = True
        except ImportError:
            print("[FilesystemWatcher] watchdog não instalado — usando polling")
            self._running = True
            asyncio.get_event_loop().create_task(self._poll_loop())

    def stop(self) -> None:
        self._running = False
        if self._observer:
            self._observer.stop()
            self._observer.join()
            self._observer = None

    def _enqueue(self, path: str) -> None:
        if self._loop:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, path)

    async def _poll_loop(self) -> None:
        seen: set[str] = set()
        while self._running:
            try:
                if os.path.isdir(self._path):
                    for fname in os.listdir(self._path):
                        if Path(fname).suffix.lower() in self.VIDEO_EXTS:
                            full = os.path.join(self._path, fname)
                            if full not in seen:
                                seen.add(full)
                                await self._queue.put(full)
            except Exception as e:
                print(f"[FilesystemWatcher] poll erro: {e}")
            await asyncio.sleep(self._poll_interval)

    async def next_file(self) -> str:
        """Wait for and return the next detected file path."""
        return await self._queue.get()

    def start_emitting(self) -> None:
        """Start publishing FileDetected events from the queue."""
        asyncio.get_event_loop().create_task(self._emit_loop())

    async def _emit_loop(self) -> None:
        from app.core.events.bus import bus, FileDetected
        while True:
            path = await self.next_file()
            await bus.publish(FileDetected(path=path))
