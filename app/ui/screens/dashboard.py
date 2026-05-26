"""Dashboard screen — poster grid with hero banner, stats and filters."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal, QSize
from PySide6.QtGui import QColor, QPainter, QFont, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QButtonGroup, QSizePolicy,
)

from app.ui.design import tokens as t
from app.utils.async_bridge import run_async


# Filter keys → display labels
FILTERS = [
    ("all",         "Todos"),
    ("airing",      "Em Exibição"),
    ("completed",   "Finalizados"),
    ("new",         "Novos Episódios"),
    ("downloading", "Baixando"),
]


class _FilterBar(QWidget):
    filter_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(t.SP2)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        for key, label in FILTERS:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setFixedHeight(32)
            btn.setProperty("filter_key", key)
            btn.setStyleSheet(self._style(False))
            btn.toggled.connect(lambda checked, b=btn, k=key: self._on_toggle(b, k, checked))
            self._group.addButton(btn)
            layout.addWidget(btn)

        layout.addStretch(1)
        # Activate "all" default
        self._group.buttons()[0].setChecked(True)

    def _style(self, active: bool) -> str:
        if active:
            return f"""
                QPushButton {{
                    background: {t.ACCENT_MUTED};
                    color: {t.ACCENT};
                    border: 1px solid {t.ACCENT};
                    border-radius: {t.RADIUS_2XL}px;
                    padding: 0 {t.SP4}px;
                    font-size: 12px;
                    font-weight: 600;
                }}
            """
        return f"""
            QPushButton {{
                background: {t.BG_ELEVATED};
                color: {t.TEXT_SECONDARY};
                border: 1px solid {t.BG_BORDER};
                border-radius: {t.RADIUS_2XL}px;
                padding: 0 {t.SP4}px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                color: {t.TEXT_PRIMARY};
                border-color: {t.TEXT_MUTED};
            }}
        """

    def _on_toggle(self, btn: QPushButton, key: str, checked: bool) -> None:
        btn.setStyleSheet(self._style(checked))
        if checked:
            self.filter_changed.emit(key)


class _StatsStrip(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(60)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(t.SP4)

        self._stats = [
            ("monitored",   "0", "Monitorados"),
            ("downloading", "0", "Baixando"),
            ("ready",       "0", "Prontos"),
            ("jobs",        "0", "Jobs Ativos"),
        ]
        self._labels: dict[str, QLabel] = {}

        for key, value, desc in self._stats:
            frame = QFrame()
            frame.setStyleSheet(f"""
                QFrame {{
                    background: {t.BG_SURFACE};
                    border: 1px solid {t.BG_BORDER};
                    border-radius: {t.RADIUS_LG}px;
                }}
            """)
            fl = QHBoxLayout(frame)
            fl.setContentsMargins(t.SP4, 0, t.SP4, 0)
            fl.setSpacing(t.SP2)

            val_lbl = QLabel(value)
            val_lbl.setStyleSheet(f"color: {t.TEXT_PRIMARY}; font-size: 18px; font-weight: 700; background: transparent;")
            desc_lbl = QLabel(desc)
            desc_lbl.setStyleSheet(f"color: {t.TEXT_MUTED}; font-size: 11px; background: transparent;")

            fl.addWidget(val_lbl)
            fl.addWidget(desc_lbl)
            fl.addStretch(1)

            self._labels[key] = val_lbl
            layout.addWidget(frame, 1)

    def update_stats(self, monitored: int, downloading: int, ready: int, jobs: int) -> None:
        self._labels["monitored"].setText(str(monitored))
        self._labels["downloading"].setText(str(downloading))
        self._labels["ready"].setText(str(ready))
        self._labels["jobs"].setText(str(jobs))


class _HeroBanner(QWidget):
    """Top hero banner showing latest downloaded or newest anime."""

    play_clicked    = Signal(int)
    watched_clicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(220)
        self._anime_id = None
        self._cover_pixmap: QPixmap | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(t.CONTENT_PAD_H, t.SP8, t.CONTENT_PAD_H, t.SP8)
        layout.setSpacing(t.SP6)

        right = QWidget()
        right.setStyleSheet("background: transparent;")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(t.SP3)

        self._title_lbl = QLabel("—")
        self._title_lbl.setStyleSheet(f"color: {t.TEXT_PRIMARY}; font-size: 32px; font-weight: 700; background: transparent;")
        self._title_lbl.setWordWrap(True)

        self._meta_lbl = QLabel("")
        self._meta_lbl.setStyleSheet(f"color: {t.TEXT_SECONDARY}; font-size: 13px; background: transparent;")

        btn_row = QWidget()
        btn_row.setStyleSheet("background: transparent;")
        brl = QHBoxLayout(btn_row)
        brl.setContentsMargins(0, 0, 0, 0)
        brl.setSpacing(t.SP3)

        self._play_btn = QPushButton("▶  ASSISTIR")
        self._play_btn.setProperty("class", "primary")
        self._play_btn.setFixedHeight(40)
        self._play_btn.setFixedWidth(160)
        self._play_btn.clicked.connect(lambda: self._anime_id and self.play_clicked.emit(self._anime_id))

        self._watched_btn = QPushButton("✓  JÁ VISTO")
        self._watched_btn.setFixedHeight(40)
        self._watched_btn.setFixedWidth(140)
        self._watched_btn.clicked.connect(lambda: self._anime_id and self.watched_clicked.emit(self._anime_id))

        brl.addWidget(self._play_btn)
        brl.addWidget(self._watched_btn)
        brl.addStretch(1)

        rl.addStretch(1)
        rl.addWidget(self._title_lbl)
        rl.addWidget(self._meta_lbl)
        rl.addWidget(btn_row)
        rl.addStretch(1)

        layout.addWidget(right, 1)

    def set_anime(self, anime_data: tuple, cover_pixmap: QPixmap | None = None) -> None:
        _, title_pattern, last_ep, res, last_date, _, official_title, airing, has_new, last_dl = anime_data
        self._anime_id = anime_data[0]
        self._cover_pixmap = cover_pixmap
        name = official_title or title_pattern
        self._title_lbl.setText(name)
        status = "Em Exibição" if airing == "Currently Airing" else "Finalizado"
        self._meta_lbl.setText(f"EP {last_ep}  ·  {status}  ·  {res}")
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # Blurred cover background
        if self._cover_pixmap:
            scaled = self._cover_pixmap.scaled(
                self.width(), self.height(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.setOpacity(0.3)
            painter.drawPixmap(x, y, scaled)
            painter.setOpacity(1.0)

        # Left-to-right fade to deep background
        from PySide6.QtGui import QLinearGradient
        grad = QLinearGradient(0, 0, self.width(), 0)
        grad.setColorAt(0.0, QColor(t.BG_DEEP))
        grad.setColorAt(0.4, QColor(0, 0, 0, 180))
        grad.setColorAt(1.0, QColor(t.BG_DEEP))
        painter.fillRect(self.rect(), grad)

        # Bottom fade
        grad2 = QLinearGradient(0, 0, 0, self.height())
        grad2.setColorAt(0.6, QColor(0, 0, 0, 0))
        grad2.setColorAt(1.0, QColor(t.BG_DEEP))
        painter.fillRect(self.rect(), grad2)


class DashboardScreen(QWidget):
    """Main dashboard — hero, stats, filter bar, and card grid."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._filter = "all"
        self._card_widgets: list = []
        self._anime_data: list[tuple] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Hero banner
        self._hero = _HeroBanner(self)
        root.addWidget(self._hero)

        # Stats + filters section
        mid = QWidget()
        ml = QVBoxLayout(mid)
        ml.setContentsMargins(t.CONTENT_PAD_H, t.SP4, t.CONTENT_PAD_H, 0)
        ml.setSpacing(t.SP4)

        self._stats = _StatsStrip(self)
        ml.addWidget(self._stats)

        self._filter_bar = _FilterBar(self)
        self._filter_bar.filter_changed.connect(self._apply_filter)
        ml.addWidget(self._filter_bar)

        root.addWidget(mid)

        # Grid scroll area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._grid_container = QWidget()
        self._grid_container.setStyleSheet("background: transparent;")
        from app.ui.utils.flow_layout import FlowLayout
        self._grid_layout = FlowLayout(self._grid_container, margin=t.CONTENT_PAD_H, h_spacing=t.CARD_GAP, v_spacing=t.CARD_GAP)
        self._scroll.setWidget(self._grid_container)
        root.addWidget(self._scroll, 1)

        # Empty state
        self._empty_label = QLabel("Nenhum anime monitorado.\nClique em + Adicionar para começar.")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet(f"color: {t.TEXT_MUTED}; font-size: 15px; background: transparent;")
        self._empty_label.hide()
        ml.addWidget(self._empty_label)

        # Load data on show
        QTimer.singleShot(0, self.refresh)

    # ── Public ──────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        run_async(self._fetch_data(), on_done=self._on_data)

    def refresh_card(self, anime_id: int) -> None:
        """Refresh a single card after a pipeline event."""
        run_async(self._fetch_data(), on_done=self._on_data)

    # ── Internal ────────────────────────────────────────────────────────────

    async def _fetch_data(self):
        from app.core.database import get_monitored_animes
        return await get_monitored_animes()

    def _on_data(self, result) -> None:
        if isinstance(result, Exception):
            return

        self._anime_data = result or []
        self._rebuild_grid()
        self._update_stats()
        self._update_hero()

    def _rebuild_grid(self) -> None:
        from app.ui.components.anime_card import AnimeCard

        # Hide before unparenting to avoid the card flashing as a top-level window
        for card in self._card_widgets:
            card.hide()
            card.setParent(None)
            card.deleteLater()
        self._card_widgets.clear()
        self._grid_layout.clear()

        if not self._anime_data:
            self._empty_label.show()
            return

        self._empty_label.hide()

        for anime in self._anime_data:
            card = AnimeCard(anime, self._grid_container)
            card.clicked.connect(self._on_card_click)
            self._grid_layout.addWidget(card)
            self._card_widgets.append(card)

        self._apply_filter(self._filter)
        # Force an immediate layout pass. Qt may trigger the layout mid-loop
        # (e.g. via setFixedSize inside AnimeCard.__init__), so the last card
        # ends up at (0,0) if we rely on the deferred event. setGeometry calls
        # _do_layout directly with the container's current rect.
        self._grid_layout.setGeometry(self._grid_container.contentsRect())

    def _apply_filter(self, key: str) -> None:
        self._filter = key
        for card in self._card_widgets:
            show = self._card_matches(card, key)
            card.setVisible(show)

    def _card_matches(self, card, key: str) -> bool:
        if key == "all":
            return True
        airing = getattr(card, "_airing_status", "")
        has_new = getattr(card, "_has_new", False)
        status  = getattr(card, "_status", "")
        if key == "airing":
            return "Airing" in airing
        if key == "completed":
            return "Finished" in airing or airing == "Completed"
        if key == "new":
            return has_new
        if key == "downloading":
            return status == "downloading"
        return True

    def _update_stats(self) -> None:
        total = len(self._anime_data)
        new_count = sum(1 for a in self._anime_data if a[8])
        self._stats.update_stats(total, 0, new_count, 0)

    def _update_hero(self) -> None:
        if not self._anime_data:
            return
        # Prefer anime with new episode
        hero_anime = next((a for a in self._anime_data if a[8]), self._anime_data[0])
        self._hero.set_anime(hero_anime)
        # Load hero cover async
        cover_path = self._get_cover_path(hero_anime)
        if cover_path:
            run_async(self._load_cover(cover_path), on_done=lambda px: self._set_hero_cover(px))

    async def _load_cover(self, path: str):
        from app.ui.utils.image_cache import get_cover_pixmap
        return get_cover_pixmap(path, 400, 220)

    def _set_hero_cover(self, result) -> None:
        if isinstance(result, Exception) or result is None:
            return
        self._hero._cover_pixmap = result
        self._hero.update()

    def _get_cover_path(self, anime: tuple) -> str | None:
        import os, re
        from app.core.config import COVERS_DIR as COVER_DIR
        safe = re.sub(r'[^\w\s-]', '', anime[1]).strip().lower().replace(' ', '_')
        for ext in (".jpg", ".png", ".jpeg", ".webp"):
            path = os.path.join(COVER_DIR, safe + ext)
            if os.path.exists(path):
                return path
        return None

    def _on_card_click(self, anime_id: int) -> None:
        from app.ui.components.detail_panel import DetailPanel
        anime = next((a for a in self._anime_data if a[0] == anime_id), None)
        if anime:
            panel = DetailPanel(anime, self.window())
            panel.exec()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(t.BG_DEEP))

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
