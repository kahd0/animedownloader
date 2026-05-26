"""Sidebar navigation button with icon, label, badge, and active indicator."""
from __future__ import annotations

from PySide6.QtCore import Qt, QRect, QSize
from PySide6.QtGui import QColor, QPainter, QFont, QFontMetrics
from PySide6.QtWidgets import QAbstractButton

from app.ui.design import tokens as t


class NavItem(QAbstractButton):
    """Navigation item: left accent border + icon + label + optional badge."""

    HEIGHT = 44

    def __init__(self, icon: str, label: str, parent=None):
        super().__init__(parent)
        self._icon   = icon
        self._label  = label
        self._badge  = 0
        self._active = False

        self.setCheckable(True)
        self.setFixedHeight(self.HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(label)

    # ── Public API ──────────────────────────────────────────────────────────

    def set_badge(self, count: int) -> None:
        self._badge = count
        self.update()

    def set_active(self, active: bool) -> None:
        self._active = active
        self.setChecked(active)
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(t.SIDEBAR_WIDTH, self.HEIGHT)

    # ── Painting ────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()

        # Background
        bg = QColor(t.BG_ELEVATED) if self._active or self.underMouse() else QColor(t.BG_SURFACE)
        painter.fillRect(r, bg)

        # Active left border
        if self._active:
            painter.fillRect(0, 0, 3, r.height(), QColor(t.ACCENT))

        # Icon (emoji / unicode glyph)
        icon_font = QFont()
        icon_font.setPixelSize(16)
        painter.setFont(icon_font)
        icon_color = QColor(t.TEXT_PRIMARY) if self._active else QColor(t.TEXT_SECONDARY)
        painter.setPen(icon_color)
        icon_rect = QRect(12, 0, 28, r.height())
        painter.drawText(icon_rect, Qt.AlignmentFlag.AlignCenter, self._icon)

        # Label
        label_font = QFont()
        label_font.setPixelSize(13)
        if self._active:
            label_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(label_font)
        painter.setPen(icon_color)
        label_rect = QRect(48, 0, r.width() - 48 - 36, r.height())
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._label)

        # Badge
        if self._badge > 0:
            badge_text = str(self._badge) if self._badge < 100 else "99+"
            badge_font = QFont()
            badge_font.setPixelSize(10)
            badge_font.setWeight(QFont.Weight.Bold)
            painter.setFont(badge_font)
            fm = QFontMetrics(badge_font)
            bw = max(fm.horizontalAdvance(badge_text) + 8, 18)
            bh = 18
            bx = r.width() - bw - 10
            by = (r.height() - bh) // 2
            painter.setBrush(QColor(t.ACCENT))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(bx, by, bw, bh, 9, 9)
            painter.setPen(QColor("white"))
            painter.drawText(QRect(bx, by, bw, bh), Qt.AlignmentFlag.AlignCenter, badge_text)
