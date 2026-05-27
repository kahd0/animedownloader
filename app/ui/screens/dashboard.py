"""Dashboard screen — poster grid with hero banner, stats and filters."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal, QSize
from PySide6.QtGui import QColor, QPainter
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


async def _compute_disk_watch_counts(animes: list) -> dict:
    """Return {anime_id: unwatched_count} based on files actually present on disk."""
    import asyncio
    import os
    from app.core.config import get_final_dir
    from app.core.naming import matches_pattern
    from app.utils.episode_parser import extract_episode_number

    final_dir = get_final_dir()
    if not os.path.isdir(final_dir):
        return {}
    try:
        files = await asyncio.to_thread(os.listdir, final_dir)
    except Exception:
        return {}

    exts = {".mkv", ".mp4", ".avi", ".mov", ".wmv"}
    video_eps = [
        (f, extract_episode_number(f))
        for f in files
        if os.path.splitext(f)[1].lower() in exts
    ]
    video_eps = [(f, ep) for f, ep in video_eps if ep is not None]

    result = {}
    for anime in animes:
        anime_id = anime[0]
        title_pat = anime[1]
        last_watched = int(anime[2] or 0)
        result[anime_id] = sum(
            1 for f, ep in video_eps
            if ep > last_watched and matches_pattern(f, title_pat)
        )
    return result


class DashboardScreen(QWidget):
    """Main dashboard — hero, stats, filter bar, and card grid."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._filter = "all"
        self._card_widgets: list = []
        self._anime_data: list[tuple] = []
        self._pending_counts: dict = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Stats + filters section
        mid = QWidget()
        ml = QVBoxLayout(mid)
        ml.setContentsMargins(t.CONTENT_PAD_H, t.SP4, t.CONTENT_PAD_H, 0)
        ml.setSpacing(t.SP4)

        # Top bar: title + add button
        top_bar = QWidget()
        tbl = QHBoxLayout(top_bar)
        tbl.setContentsMargins(0, 0, 0, 0)
        tbl.setSpacing(t.SP4)

        dash_title = QLabel("Dashboard")
        dash_title.setStyleSheet(
            f"color: {t.TEXT_PRIMARY}; font-size: 22px; font-weight: 700; background: transparent;"
        )
        tbl.addWidget(dash_title)
        tbl.addStretch(1)

        add_btn = QPushButton("+ Adicionar")
        add_btn.setProperty("class", "primary")
        add_btn.setFixedHeight(36)
        add_btn.clicked.connect(self._on_add_clicked)
        tbl.addWidget(add_btn)

        ml.addWidget(top_bar)

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

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh()

    # ── Public ──────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        run_async(self._fetch_data(), on_done=self._on_data)

    def refresh_card(self, anime_id: int) -> None:
        """Refresh a single card after a pipeline event."""
        run_async(self._fetch_data(), on_done=self._on_data)

    # ── Internal ────────────────────────────────────────────────────────────

    async def _fetch_data(self):
        from app.core.database import get_monitored_animes, get_all_pending_counts
        animes = await get_monitored_animes()
        counts = await get_all_pending_counts()
        disk_counts = await _compute_disk_watch_counts(animes or [])
        for anime_id, watch_count in disk_counts.items():
            counts.setdefault(anime_id, {})["watch_count"] = watch_count
        return animes, counts

    def _on_data(self, result) -> None:
        if isinstance(result, Exception):
            return

        animes, counts = result
        self._anime_data = animes or []
        self._pending_counts = counts or {}
        self._rebuild_grid()
        self._update_stats()

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
            pending = self._pending_counts.get(anime[0], {})
            card = AnimeCard(anime, self._grid_container, pending_counts=pending)
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

    def _on_card_click(self, anime_id: int) -> None:
        from app.ui.components.detail_panel import DetailPanel
        anime = next((a for a in self._anime_data if a[0] == anime_id), None)
        if anime:
            panel = DetailPanel(anime, self.window())
            panel.exec()

    def _on_add_clicked(self) -> None:
        window = self.window()
        if hasattr(window, "show_add_anime"):
            window.show_add_anime()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(t.BG_DEEP))

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
