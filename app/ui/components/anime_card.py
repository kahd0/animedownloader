"""AnimeCard — cinematographic poster card with hover scale and status chip."""
from __future__ import annotations

import os
from PySide6.QtCore import (
    Qt, Signal, QSize, QRect, QTimer,
)
from PySide6.QtGui import (
    QColor, QPainter, QPixmap, QLinearGradient, QFont,
    QFontMetrics, QPainterPath,
)
from PySide6.QtWidgets import QWidget, QToolTip

from app.ui.design import tokens as t
from app.ui.utils.image_cache import get_cover_pixmap


class AnimeCard(QWidget):
    clicked = Signal(int)  # anime_id

    W = t.CARD_WIDTH
    H = t.CARD_HEIGHT
    POSTER_H = int(H * 0.76)  # ~250px

    def __init__(self, anime_data: tuple, parent=None):
        super().__init__(parent)
        _, title_p, last_ep, res, last_date, cover_url, official, airing, has_new, last_dl = anime_data
        self._anime_id    = anime_data[0]
        self._title       = official or title_p
        self._title_pat   = title_p
        self._episode     = last_ep
        self._airing_status = airing or ""
        self._has_new     = bool(has_new)
        self._status      = "airing"  # will be updated by events
        self._cover: QPixmap | None = None
        self._hover_opacity: float = 0.0

        self.setFixedSize(self.W, self.H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)

        # Use QVariantAnimation (no Qt Property needed)
        from PySide6.QtCore import QVariantAnimation
        self._scale: float = 1.0
        self._scale_anim = QVariantAnimation(self)
        self._scale_anim.setDuration(t.DUR_FAST)
        self._scale_anim.valueChanged.connect(lambda v: self._set_scale(float(v)))

        self._overlay_anim = QVariantAnimation(self)
        self._overlay_anim.setDuration(t.DUR_FAST)
        self._overlay_anim.valueChanged.connect(lambda v: self._set_overlay(float(v)))

        # Load cover image
        self._load_cover()

    def _set_scale(self, v: float) -> None:
        self._scale = v
        self.update()

    def _set_overlay(self, v: float) -> None:
        self._hover_opacity = v
        self.update()

    # ── Cover loading ────────────────────────────────────────────────────────

    def _load_cover(self) -> None:
        path = self._find_cover_path()
        if path:
            px = get_cover_pixmap(path, self.W, self.POSTER_H)
            if px and not px.isNull():
                self._cover = px
                self.update()
            return
        # Try async download if URL is in DB
        QTimer.singleShot(100, self._try_async_cover)

    def _find_cover_path(self) -> str | None:
        try:
            import re
            from app.core.config import COVERS_DIR as COVER_DIR
            safe = re.sub(r'[^\w\s-]', '', self._title_pat).strip().lower().replace(' ', '_')
            for ext in (".jpg", ".png", ".jpeg", ".webp"):
                path = os.path.join(COVER_DIR, safe + ext)
                if os.path.exists(path):
                    return path
        except Exception:
            pass
        return None

    def _try_async_cover(self) -> None:
        pass  # Cover download handled by downloader on anime add

    def set_cover(self, pixmap: QPixmap) -> None:
        self._cover = pixmap
        self.update()

    def set_status(self, status: str) -> None:
        self._status = status
        self.update()

    # ── Painting ─────────────────────────────────────────────────────────────

    def sizeHint(self) -> QSize:
        return QSize(self.W, self.H)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # Apply scale transform from center
        cx = self.width() / 2
        cy = self.height() / 2
        painter.translate(cx, cy)
        painter.scale(self._scale, self._scale)
        painter.translate(-cx, -cy)

        r = self.rect()
        poster_rect = QRect(0, 0, self.W, self.POSTER_H)

        # Card background
        path = QPainterPath()
        path.addRoundedRect(r, t.RADIUS_LG, t.RADIUS_LG)
        painter.setClipPath(path)
        painter.fillRect(r, QColor(t.BG_SURFACE))

        # Cover image or placeholder
        if self._cover and not self._cover.isNull():
            painter.drawPixmap(poster_rect, self._cover)
        else:
            painter.fillRect(poster_rect, QColor(t.BG_ELEVATED))
            # Placeholder icon
            painter.setPen(QColor(t.BG_BORDER))
            font = QFont()
            font.setPixelSize(32)
            painter.setFont(font)
            painter.drawText(poster_rect, Qt.AlignmentFlag.AlignCenter, "▶")

        # Gradient overlay (bottom fade over poster)
        grad = QLinearGradient(0, self.POSTER_H - 80, 0, self.POSTER_H)
        grad.setColorAt(0.0, QColor(0, 0, 0, 0))
        grad.setColorAt(1.0, QColor(t.BG_SURFACE))
        painter.fillRect(QRect(0, self.POSTER_H - 80, self.W, 80), grad)

        # NOVO badge
        if self._has_new:
            badge_font = QFont()
            badge_font.setPixelSize(9)
            badge_font.setWeight(QFont.Weight.Bold)
            painter.setFont(badge_font)
            bw, bh = 44, 20
            bx = self.W - bw - 8
            painter.setBrush(QColor(t.NEW_EPISODE))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(bx, 10, bw, bh, 10, 10)
            painter.setPen(QColor("white"))
            painter.drawText(QRect(bx, 10, bw, bh), Qt.AlignmentFlag.AlignCenter, "NOVO")

        # Status chip (bottom left of poster)
        status = self._get_status_display()
        if status is not None:
            status_text, status_color = status
            chip_font = QFont()
            chip_font.setPixelSize(10)
            chip_font.setWeight(QFont.Weight.DemiBold)
            painter.setFont(chip_font)
            cfm = QFontMetrics(chip_font)
            cw = cfm.horizontalAdvance(status_text) + 16
            ch = 20
            cx_chip = 10
            cy_chip = self.POSTER_H - ch - 10
            painter.setBrush(QColor(status_color + "CC"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(cx_chip, cy_chip, cw, ch, 10, 10)
            painter.setPen(QColor("white"))
            painter.drawText(QRect(cx_chip, cy_chip, cw, ch), Qt.AlignmentFlag.AlignCenter, status_text)

        # Title text below poster
        title_rect = QRect(t.SP3, self.POSTER_H + t.SP2, self.W - t.SP6, 36)
        title_font = QFont()
        title_font.setPixelSize(13)
        title_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(title_font)
        painter.setPen(QColor(t.TEXT_PRIMARY))
        tfm = QFontMetrics(title_font)
        elided = tfm.elidedText(self._title, Qt.TextElideMode.ElideRight, title_rect.width())
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, elided)

        # Episode
        ep_font = QFont()
        ep_font.setPixelSize(11)
        painter.setFont(ep_font)
        painter.setPen(QColor(t.TEXT_SECONDARY))
        ep_rect = QRect(t.SP3, self.POSTER_H + t.SP2 + 20, self.W - t.SP6, 20)
        ep_text = f"EP {self._episode:02d}" if self._episode else "—"
        painter.drawText(ep_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, ep_text)

        # Hover overlay
        if self._hover_opacity > 0.01:
            overlay_color = QColor(0, 0, 0, int(180 * self._hover_opacity))
            painter.fillRect(poster_rect, overlay_color)

            # Play button
            play_font = QFont()
            play_font.setPixelSize(32)
            painter.setFont(play_font)
            painter.setPen(QColor(255, 255, 255, int(255 * self._hover_opacity)))
            painter.drawText(poster_rect, Qt.AlignmentFlag.AlignCenter, "▶")

        painter.setClipping(False)

    def _get_status_display(self) -> tuple[str, str] | None:
        airing = self._airing_status
        if self._status == "downloading":
            return "BAIXANDO", t.DOWNLOADING
        if self._status == "translating":
            return "TRADUZINDO", t.TRANSLATING
        if self._status == "error":
            return "ERRO", t.ERROR
        if "Currently Airing" in airing:
            return "EM EXIBIÇÃO", t.SUCCESS
        if "Finished" in airing or "Completed" in airing:
            return "FINALIZADO", t.TEXT_MUTED
        if "Not yet aired" in airing:
            return "EM BREVE", t.INFO
        return None

    # ── Mouse events ─────────────────────────────────────────────────────────

    def enterEvent(self, event):
        self._scale_anim.stop()
        self._scale_anim.setStartValue(self._scale)
        self._scale_anim.setEndValue(1.03)
        self._scale_anim.start()

        self._overlay_anim.stop()
        self._overlay_anim.setStartValue(self._hover_opacity)
        self._overlay_anim.setEndValue(1.0)
        self._overlay_anim.start()

    def leaveEvent(self, event):
        self._scale_anim.stop()
        self._scale_anim.setStartValue(self._scale)
        self._scale_anim.setEndValue(1.0)
        self._scale_anim.start()

        self._overlay_anim.stop()
        self._overlay_anim.setStartValue(self._hover_opacity)
        self._overlay_anim.setEndValue(0.0)
        self._overlay_anim.start()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._anime_id)
