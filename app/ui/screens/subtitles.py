"""Subtitles screen — subtitle status per anime."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QFrame, QPushButton,
)

from app.ui.design import tokens as t
from app.utils.async_bridge import run_async


class SubtitlesScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        topbar = QWidget()
        topbar.setFixedHeight(56)
        tbl = QHBoxLayout(topbar)
        tbl.setContentsMargins(t.CONTENT_PAD_H, 0, t.CONTENT_PAD_H, 0)

        title = QLabel("Legendas")
        title.setStyleSheet(f"color: {t.TEXT_PRIMARY}; font-size: 22px; font-weight: 700; background: transparent;")
        tbl.addWidget(title)
        tbl.addStretch(1)
        root.addWidget(topbar)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {t.BG_BORDER}; border: none;")
        root.addWidget(sep)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._container = QWidget()
        self._container.setStyleSheet("background: transparent;")
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(t.CONTENT_PAD_H, t.SP6, t.CONTENT_PAD_H, t.SP6)
        self._layout.setSpacing(t.SP3)
        self._layout.addStretch(1)
        scroll.setWidget(self._container)
        root.addWidget(scroll, 1)

        QTimer.singleShot(0, self.refresh)

    def refresh(self) -> None:
        run_async(self._fetch(), on_done=self._on_data)

    async def _fetch(self):
        import aiosqlite
        from app.core.config import DB_PATH
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT m.id, m.official_title, m.title_pattern, "
                "sc.provider, sc.language, sc.filename, sc.created_at "
                "FROM monitored m "
                "LEFT JOIN subtitle_cache sc ON sc.anime_id = m.id "
                "ORDER BY m.official_title"
            ) as cur:
                return await cur.fetchall()

    def _on_data(self, result) -> None:
        if isinstance(result, Exception):
            return

        layout = self._layout
        while layout.count() > 1:
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        rows = result or []
        for row in rows:
            card = _SubtitleCard(row)
            layout.insertWidget(layout.count() - 1, card)

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()


class _SubtitleCard(QWidget):
    PROVIDER_COLORS = {
        "opensubtitles": t.TRANSLATING,
        "jimaku":        t.WARNING,
    }

    refetch_requested = None  # set per-instance below

    def __init__(self, row: tuple, parent=None):
        super().__init__(parent)
        anime_id, official, pattern, provider, language, filename, created = row
        self._anime_id = anime_id
        self._pattern = pattern
        name = official or pattern

        self.setFixedHeight(64)
        self.setStyleSheet(f"""
            QWidget {{
                background: {t.BG_SURFACE};
                border: 1px solid {t.BG_BORDER};
                border-radius: {t.RADIUS_LG}px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(t.SP4, 0, t.SP4, 0)
        layout.setSpacing(t.SP4)

        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(f"color: {t.TEXT_PRIMARY}; font-size: 13px; font-weight: 600; background: transparent; border: none;")

        if provider:
            pcolor = self.PROVIDER_COLORS.get(provider.lower(), t.TEXT_SECONDARY)
            pchip = QLabel(provider)
            pchip.setFixedHeight(22)
            pchip.setStyleSheet(f"""
                color: {pcolor};
                background: {pcolor}33;
                border: 1px solid {pcolor};
                border-radius: 11px;
                padding: 0 8px;
                font-size: 11px;
                font-weight: 600;
            """)
        else:
            pchip = QLabel("Sem legenda")
            pchip.setStyleSheet(f"color: {t.TEXT_MUTED}; background: transparent; border: none; font-size: 11px;")

        lang_lbl = QLabel((language or "").upper() if language else "—")
        lang_lbl.setStyleSheet(f"color: {t.TEXT_SECONDARY}; background: transparent; border: none; font-size: 12px;")
        lang_lbl.setFixedWidth(48)

        layout.addWidget(name_lbl, 1)
        layout.addWidget(lang_lbl)
        layout.addWidget(pchip)

        if provider:
            re_btn = QPushButton("Re-buscar")
            re_btn.setFixedHeight(28)
            re_btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {t.ACCENT};
                    border: 1px solid {t.ACCENT};
                    border-radius: {t.RADIUS_SM}px;
                    padding: 0 8px;
                    font-size: 11px;
                }}
                QPushButton:hover {{ background: {t.ACCENT_MUTED}; }}
            """)
            re_btn.clicked.connect(self._on_refetch)
            layout.addWidget(re_btn)

    def _on_refetch(self) -> None:
        try:
            from app.core.jobs.queue import job_queue
            from app.utils.async_bridge import run_async
            run_async(
                job_queue.enqueue("subtitle", anime_id=self._anime_id),
                on_done=self._on_refetch_queued,
            )
        except Exception as e:
            print(f"Re-fetch error: {e}")

    def _on_refetch_queued(self, result) -> None:
        try:
            from app.ui.components.toast import ToastManager
            if isinstance(result, Exception):
                ToastManager.instance().show("Erro ao enfileirar busca de legenda", "error")
            else:
                ToastManager.instance().show(f"Busca de legenda enfileirada — {self._pattern}", "info")
        except Exception:
            pass
