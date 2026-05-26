"""Main sidebar with navigation items and active-job status footer."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor, QPainter, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFrame, QSizePolicy,
)

from app.ui.design import tokens as t
from app.ui.sidebar.nav_item import NavItem


# (screen_key, icon, label)
NAV_ITEMS = [
    ("dashboard",  "⊞",  "Dashboard"),
    ("library",    "☰",  "Monitorados"),
    ("downloads",  "⬇",  "Downloads"),
    ("subtitles",  "CC", "Legendas"),
    ("pipeline",   "◎",  "Pipeline"),
    ("logs",       "≡",  "Logs"),
    ("settings",   "⚙",  "Configurações"),
]


class _StatusFooter(QWidget):
    """Small job-count indicator at the bottom of the sidebar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(56)
        self._count = 0
        self._label_text = "Ocioso"

    def set_status(self, count: int, label: str) -> None:
        self._count = count
        self._label_text = label
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()

        painter.fillRect(r, QColor(t.BG_SURFACE))

        # Top separator
        painter.setPen(QColor(t.BG_BORDER))
        painter.drawLine(0, 0, r.width(), 0)

        # Dot indicator
        dot_color = QColor(t.SUCCESS) if self._count > 0 else QColor(t.TEXT_MUTED)
        painter.setBrush(dot_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(14, r.height() // 2 - 4, 8, 8)

        # Count + label
        font = QFont()
        font.setPixelSize(12)
        painter.setFont(font)
        painter.setPen(QColor(t.TEXT_SECONDARY if self._count == 0 else t.TEXT_PRIMARY))
        text = f"{self._count} jobs" if self._count > 0 else self._label_text
        from PySide6.QtCore import QRect
        painter.drawText(QRect(30, 0, r.width() - 30, r.height()), Qt.AlignmentFlag.AlignVCenter, text)


class Sidebar(QWidget):
    """Left navigation sidebar."""

    nav_changed = Signal(str)  # emits screen key

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(t.SIDEBAR_WIDTH)
        self.setObjectName("sidebar")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Top spacer (title bar occupies the same row visually)
        spacer_top = QWidget()
        spacer_top.setFixedHeight(t.TITLEBAR_HEIGHT)
        layout.addWidget(spacer_top)

        # Nav items
        self._items: dict[str, NavItem] = {}
        for key, icon, label in NAV_ITEMS:
            item = NavItem(icon, label, self)
            item.clicked.connect(lambda checked, k=key: self._on_nav(k))
            self._items[key] = item
            layout.addWidget(item)

        layout.addStretch(1)

        # Status footer
        self._footer = _StatusFooter(self)
        layout.addWidget(self._footer)

        # Activate default
        self.set_active("dashboard")

        # Poll job queue every 3s
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll_jobs)
        self._timer.start(3000)

    def set_active(self, key: str) -> None:
        for k, item in self._items.items():
            item.set_active(k == key)

    def set_badge(self, key: str, count: int) -> None:
        if key in self._items:
            self._items[key].set_badge(count)

    def _on_nav(self, key: str) -> None:
        self.set_active(key)
        self.nav_changed.emit(key)

    def _poll_jobs(self) -> None:
        from app.utils.async_bridge import run_async
        try:
            from app.core.jobs.queue import job_queue
            run_async(job_queue.get_status(), on_done=self._on_jobs)
        except Exception:
            pass

    def _on_jobs(self, result) -> None:
        if isinstance(result, Exception):
            return
        jobs = result or []
        running = [j for j in jobs if (j.get("status") if isinstance(j, dict) else getattr(j, "status", None)) == "running"]
        count = len(running)
        if running:
            j0 = running[0]
            label = j0.get("type", "Ocioso") if isinstance(j0, dict) else getattr(j0, "type", "Ocioso")
        else:
            label = "Ocioso"
        self._footer.set_status(count, label)
        self.set_badge("pipeline", count)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(t.BG_SURFACE))
        # Right border separator
        painter.setPen(QColor(t.BG_BORDER))
        painter.drawLine(self.width() - 1, 0, self.width() - 1, self.height())
