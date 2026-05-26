"""Skeleton loading card with shimmer animation."""
from __future__ import annotations

from PySide6.QtCore import QPropertyAnimation, QVariantAnimation, Qt, QRect, QSize
from PySide6.QtGui import QColor, QPainter, QLinearGradient, QPainterPath
from PySide6.QtWidgets import QWidget

from app.ui.design import tokens as t


class SkeletonCard(QWidget):
    W = t.CARD_WIDTH
    H = t.CARD_HEIGHT

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.W, self.H)
        self._shimmer_x: float = -self.W

        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(float(-self.W))
        self._anim.setEndValue(float(self.W * 2))
        self._anim.setDuration(1200)
        self._anim.setLoopCount(-1)  # infinite
        self._anim.valueChanged.connect(self._on_shimmer)
        self._anim.start()

    def _on_shimmer(self, value) -> None:
        self._shimmer_x = float(value)
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(self.W, self.H)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(self.rect(), t.RADIUS_LG, t.RADIUS_LG)
        painter.setClipPath(path)

        # Base fill
        painter.fillRect(self.rect(), QColor(t.BG_SURFACE))

        # Shimmer gradient
        sx = int(self._shimmer_x)
        grad = QLinearGradient(sx, 0, sx + self.W, 0)
        grad.setColorAt(0.0, QColor(t.BG_SURFACE))
        grad.setColorAt(0.4, QColor(t.BG_ELEVATED))
        grad.setColorAt(0.6, QColor(t.BG_ELEVATED))
        grad.setColorAt(1.0, QColor(t.BG_SURFACE))
        painter.fillRect(self.rect(), grad)

        # Content skeleton blocks
        painter.setBrush(QColor(t.BG_BORDER))
        painter.setPen(Qt.PenStyle.NoPen)

        poster_rect = QRect(0, 0, self.W, int(self.H * 0.76))
        painter.fillRect(poster_rect, QColor(t.BG_ELEVATED))

        # Title block
        painter.drawRoundedRect(t.SP3, self.H - 56, self.W - t.SP6, 12, 6, 6)
        # Subtitle block
        painter.drawRoundedRect(t.SP3, self.H - 36, (self.W - t.SP6) // 2, 10, 5, 5)

    def stop(self) -> None:
        self._anim.stop()

    def hideEvent(self, event):
        self._anim.stop()
        super().hideEvent(event)

    def showEvent(self, event):
        self._anim.start()
        super().showEvent(event)
