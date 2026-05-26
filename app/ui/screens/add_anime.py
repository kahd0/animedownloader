"""Add Anime overlay — slides in from right over any screen."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QRect, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QScrollArea, QFrame, QComboBox, QSpinBox, QCheckBox,
)

from app.ui.design import tokens as t
from app.utils.async_bridge import run_async


class AddAnimeOverlay(QWidget):
    """Full-screen overlay slide-in panel for adding a new anime."""

    anime_added = Signal(str)  # emits title_pattern on success

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.timeout.connect(self._do_search)
        self._selected_anime: dict | None = None

        self.hide()
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setFixedHeight(56)
        header.setStyleSheet(f"background: {t.BG_SURFACE}; border-bottom: 1px solid {t.BG_BORDER};")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(t.CONTENT_PAD_H, 0, t.CONTENT_PAD_H, 0)

        title = QLabel("Adicionar Anime")
        title.setStyleSheet(f"color: {t.TEXT_PRIMARY}; font-size: 20px; font-weight: 700; background: transparent;")
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(36, 36)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {t.TEXT_MUTED};
                border: none;
                font-size: 16px;
            }}
            QPushButton:hover {{ color: {t.TEXT_PRIMARY}; }}
        """)
        close_btn.clicked.connect(self.close_overlay)
        hl.addWidget(title)
        hl.addStretch(1)
        hl.addWidget(close_btn)
        layout.addWidget(header)

        # Main content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(t.CONTENT_PAD_H, t.SP6, t.CONTENT_PAD_H, t.SP8)
        cl.setSpacing(t.SP5)

        # Search input
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("🔍  Buscar anime por título...")
        self._search_input.setFixedHeight(48)
        self._search_input.setStyleSheet(f"""
            QLineEdit {{
                background: {t.BG_ELEVATED};
                border: 2px solid {t.BG_BORDER};
                border-radius: {t.RADIUS_LG}px;
                padding: 0 {t.SP4}px;
                color: {t.TEXT_PRIMARY};
                font-size: 15px;
            }}
            QLineEdit:focus {{ border-color: {t.ACCENT}; }}
        """)
        self._search_input.textChanged.connect(lambda: self._search_debounce.start(300))
        cl.addWidget(self._search_input)

        # Results area
        results_label = QLabel("RESULTADOS")
        results_label.setStyleSheet(f"color: {t.TEXT_MUTED}; font-size: 11px; font-weight: 600; letter-spacing: 1px; background: transparent;")
        cl.addWidget(results_label)

        self._results_container = QWidget()
        self._results_container.setStyleSheet("background: transparent;")
        self._results_layout = QVBoxLayout(self._results_container)
        self._results_layout.setContentsMargins(0, 0, 0, 0)
        self._results_layout.setSpacing(t.SP2)
        cl.addWidget(self._results_container)

        # Selected anime panel (hidden by default)
        self._selected_panel = _SelectedAnimePanel(self)
        self._selected_panel.add_clicked.connect(self._add_anime)
        self._selected_panel.hide()
        cl.addWidget(self._selected_panel)

        cl.addStretch(1)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

    def open_overlay(self) -> None:
        parent = self.parentWidget()
        if parent:
            self.setGeometry(parent.rect())
        self.show()
        self.raise_()
        # Slide in from right
        end_rect = self.geometry()
        start_rect = QRect(end_rect.right(), end_rect.top(), 0, end_rect.height())
        self._anim = QPropertyAnimation(self, b"geometry")
        self._anim.setDuration(t.DUR_NORMAL)
        self._anim.setStartValue(start_rect)
        self._anim.setEndValue(end_rect)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.start()

    def close_overlay(self) -> None:
        self.hide()
        self._selected_panel.hide()
        self._search_input.clear()
        self._clear_results()

    def _do_search(self) -> None:
        query = self._search_input.text().strip()
        if len(query) < 2:
            self._clear_results()
            return
        run_async(self._search_async(query), on_done=self._on_results)

    async def _search_async(self, query: str):
        try:
            from app.providers.rss.subsplease import SubsPleaseProvider
            provider = SubsPleaseProvider()
            results = await provider.search_history(query)
            return results[:20]
        except Exception:
            try:
                from app.core.api import search_anime_history
                return await search_anime_history(query)
            except Exception as e:
                return e

    def _on_results(self, result) -> None:
        self._clear_results()
        if isinstance(result, Exception) or not result:
            empty = QLabel("Nenhum resultado encontrado.")
            empty.setStyleSheet(f"color: {t.TEXT_MUTED}; font-size: 13px; background: transparent;")
            self._results_layout.addWidget(empty)
            return

        for item in result:
            row = _ResultRow(item)
            row.clicked.connect(self._on_result_select)
            self._results_layout.addWidget(row)

    def _clear_results(self) -> None:
        while self._results_layout.count():
            child = self._results_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _on_result_select(self, data: dict) -> None:
        self._selected_anime = data
        self._selected_panel.set_anime(data)
        self._selected_panel.show()

    def _add_anime(self, config: dict) -> None:
        if not self._selected_anime:
            return
        run_async(self._do_add(config), on_done=self._on_added)

    async def _do_add(self, config: dict):
        from app.core.downloader import add_anime
        title = self._selected_anime.get("title", "")
        episode = config.get("start_episode", 0)
        resolution = config.get("resolution", "1080p")
        return await add_anime(title, episode, resolution)

    def _on_added(self, result) -> None:
        if isinstance(result, Exception):
            return
        title = self._selected_anime.get("title", "") if self._selected_anime else ""
        self.anime_added.emit(title)
        self.close_overlay()
        try:
            from app.ui.components.toast import ToastManager
            ToastManager.instance().show(f"Anime adicionado: {title}", "success")
        except Exception:
            pass

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(t.BG_DEEP + "F0"))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.parentWidget():
            self.setGeometry(self.parentWidget().rect())


class _ResultRow(QWidget):
    clicked = Signal(dict)

    def __init__(self, data: dict, parent=None):
        super().__init__(parent)
        self._data = data
        self.setFixedHeight(56)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QWidget {{
                background: {t.BG_SURFACE};
                border: 1px solid {t.BG_BORDER};
                border-radius: {t.RADIUS_MD}px;
            }}
            QWidget:hover {{
                background: {t.BG_ELEVATED};
                border-color: {t.ACCENT};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(t.SP4, 0, t.SP4, 0)
        layout.setSpacing(t.SP4)

        title = data.get("title") or data.get("name") or str(data)
        meta = data.get("episode_count") or data.get("episodes") or ""

        name_lbl = QLabel(title)
        name_lbl.setStyleSheet(f"color: {t.TEXT_PRIMARY}; font-size: 13px; font-weight: 600; background: transparent; border: none;")

        if meta:
            meta_lbl = QLabel(str(meta))
            meta_lbl.setStyleSheet(f"color: {t.TEXT_MUTED}; font-size: 12px; background: transparent; border: none;")
            layout.addWidget(name_lbl, 1)
            layout.addWidget(meta_lbl)
        else:
            layout.addWidget(name_lbl, 1)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._data)


class _SelectedAnimePanel(QFrame):
    add_clicked = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background: {t.BG_SURFACE};
                border: 1px solid {t.BG_BORDER};
                border-radius: {t.RADIUS_XL}px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(t.SP6, t.SP5, t.SP6, t.SP5)
        layout.setSpacing(t.SP4)

        self._title_lbl = QLabel("")
        self._title_lbl.setStyleSheet(f"color: {t.TEXT_PRIMARY}; font-size: 18px; font-weight: 700; background: transparent;")
        self._title_lbl.setWordWrap(True)
        layout.addWidget(self._title_lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background: {t.BG_BORDER}; border: none;")
        layout.addWidget(sep)

        # Config row
        config_row = QWidget()
        config_row.setStyleSheet("background: transparent;")
        cr = QHBoxLayout(config_row)
        cr.setContentsMargins(0, 0, 0, 0)
        cr.setSpacing(t.SP6)

        # Resolution
        res_w = QWidget()
        res_w.setStyleSheet("background: transparent;")
        rw = QVBoxLayout(res_w)
        rw.setContentsMargins(0, 0, 0, 0)
        rw.setSpacing(4)
        rw.addWidget(QLabel("Resolução"))
        self._res_combo = QComboBox()
        self._res_combo.addItems(["1080p", "720p", "480p"])
        rw.addWidget(self._res_combo)
        cr.addWidget(res_w)

        # Start episode
        ep_w = QWidget()
        ep_w.setStyleSheet("background: transparent;")
        ew = QVBoxLayout(ep_w)
        ew.setContentsMargins(0, 0, 0, 0)
        ew.setSpacing(4)
        ew.addWidget(QLabel("Ep. inicial"))
        self._ep_spin = QSpinBox()
        self._ep_spin.setMinimum(0)
        self._ep_spin.setMaximum(9999)
        self._ep_spin.setFixedWidth(80)
        ew.addWidget(self._ep_spin)
        cr.addWidget(ep_w)

        # Toggles
        tog_w = QWidget()
        tog_w.setStyleSheet("background: transparent;")
        tw = QVBoxLayout(tog_w)
        tw.setContentsMargins(0, 0, 0, 0)
        tw.setSpacing(4)
        self._sub_cb = QCheckBox("Auto-legenda")
        self._sub_cb.setChecked(True)
        self._tl_cb = QCheckBox("Auto-traduzir")
        self._tl_cb.setChecked(True)
        tw.addWidget(self._sub_cb)
        tw.addWidget(self._tl_cb)
        cr.addWidget(tog_w)

        cr.addStretch(1)
        layout.addWidget(config_row)

        # Add button
        add_btn = QPushButton("+ ADICIONAR ANIME")
        add_btn.setProperty("class", "primary")
        add_btn.setFixedHeight(44)
        add_btn.clicked.connect(self._on_add)
        layout.addWidget(add_btn)

    def set_anime(self, data: dict) -> None:
        title = data.get("title") or data.get("name") or ""
        self._title_lbl.setText(title)
        ep = data.get("episode_count") or data.get("episodes")
        if ep:
            try:
                self._ep_spin.setValue(max(0, int(ep) - 2))
            except Exception:
                pass

    def _on_add(self) -> None:
        self.add_clicked.emit({
            "resolution":    self._res_combo.currentText(),
            "start_episode": self._ep_spin.value(),
            "auto_subtitle": self._sub_cb.isChecked(),
            "auto_translate":self._tl_cb.isChecked(),
        })
