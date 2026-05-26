"""LRU cache for QPixmap covers — Qt main-thread only."""
from __future__ import annotations

from functools import lru_cache
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt, QThread, QCoreApplication


@lru_cache(maxsize=300)
def get_cover_pixmap(path: str, width: int, height: int) -> QPixmap | None:
    """Return a scaled QPixmap for the given cover path (cached).

    Must only be called from the Qt main thread — QPixmap is not thread-safe.
    Returns None silently if called from a background thread.
    """
    app = QCoreApplication.instance()
    if app is not None and QThread.currentThread() is not app.thread():
        return None
    try:
        px = QPixmap(path)
        if px.isNull():
            return None
        return px.scaled(width, height,
                         Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                         Qt.TransformationMode.SmoothTransformation)
    except Exception:
        return None


def get_cover_pixmap_sync(path: str, width: int, height: int) -> QPixmap | None:
    return get_cover_pixmap(path, width, height)


def invalidate(path: str | None = None) -> None:
    """Clear cache entirely (path parameter ignored — lru_cache has no per-key invalidation)."""
    get_cover_pixmap.cache_clear()
