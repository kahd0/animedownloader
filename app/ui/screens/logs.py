"""Logs screen — virtual-scroll log viewer with level/source filters."""
from __future__ import annotations

from collections import deque
from PySide6.QtCore import (
    Qt, QAbstractListModel, QModelIndex, QSize, QTimer, Signal,
)
from PySide6.QtGui import QColor, QPainter, QFont, QFontMetrics
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListView, QLineEdit, QFrame, QButtonGroup, QCheckBox,
)

from app.ui.design import tokens as t
from app.ui.design.fonts import mono_font


class _LogEntry:
    __slots__ = ("timestamp", "level", "source", "message", "expanded")

    def __init__(self, timestamp: str, level: str, source: str, message: str):
        self.timestamp = timestamp
        self.level     = level
        self.source    = source
        self.message   = message
        self.expanded  = False


class LogModel(QAbstractListModel):
    MAX = 50_000

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries: deque[_LogEntry] = deque(maxlen=self.MAX)
        self._visible: list[_LogEntry] = []
        self._level_filter: set[str] = {"INFO", "WARNING", "ERROR", "DEBUG", "SUCCESS"}
        self._search: str = ""

    def append(self, entry: _LogEntry) -> None:
        self._entries.append(entry)
        if self._matches(entry):
            row = len(self._visible)
            self.beginInsertRows(QModelIndex(), row, row)
            self._visible.append(entry)
            self.endInsertRows()

    def rebuild_visible(self) -> None:
        self.beginResetModel()
        self._visible = [e for e in self._entries if self._matches(e)]
        self.endResetModel()

    def set_level_filter(self, levels: set[str]) -> None:
        self._level_filter = levels
        self.rebuild_visible()

    def set_search(self, text: str) -> None:
        self._search = text.lower()
        self.rebuild_visible()

    def _matches(self, e: _LogEntry) -> bool:
        if e.level.upper() not in self._level_filter:
            return False
        if self._search and self._search not in e.message.lower():
            return False
        return True

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._visible)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._visible):
            return None
        entry = self._visible[index.row()]
        if role == Qt.ItemDataRole.UserRole:
            return entry
        if role == Qt.ItemDataRole.SizeHintRole:
            return QSize(0, 36)
        return None

    def toggle_expand(self, row: int) -> None:
        if 0 <= row < len(self._visible):
            self._visible[row].expanded = not self._visible[row].expanded
            idx = self.index(row)
            self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.SizeHintRole])


class _LogDelegate:
    # We implement as a QStyledItemDelegate below
    pass


from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem


class LogEntryDelegate(QStyledItemDelegate):
    LEVEL_COLORS = {
        "INFO":    t.INFO,
        "WARNING": t.WARNING,
        "ERROR":   t.ERROR,
        "DEBUG":   t.TEXT_MUTED,
        "SUCCESS": t.SUCCESS,
    }
    SOURCE_COLORS = {
        "pipeline":    t.ACCENT,
        "rss":         t.ACCENT,
        "torrent":     t.DOWNLOADING,
        "download":    t.DOWNLOADING,
        "subtitle":    t.SUCCESS,
        "translation": t.TRANSLATING,
        "organize":    t.WARNING,
    }

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        entry: _LogEntry | None = index.data(Qt.ItemDataRole.UserRole)
        if entry and entry.expanded:
            return QSize(option.rect.width(), 36 + 20 * len(entry.message.split("\\n")))
        return QSize(option.rect.width(), 36)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        painter.save()
        entry: _LogEntry | None = index.data(Qt.ItemDataRole.UserRole)
        if entry is None:
            painter.restore()
            return

        r = option.rect

        # Hover / selection
        hovered = bool(option.state & __import__(
            "PySide6.QtWidgets", fromlist=["QStyle"]
        ).QStyle.StateFlag.State_MouseOver)
        if hovered:
            painter.fillRect(r, QColor(t.BG_ELEVATED))

        # Timestamp
        mono = mono_font(11)
        painter.setFont(mono)
        painter.setPen(QColor(t.TEXT_MUTED))
        ts_w = 80
        painter.drawText(r.adjusted(12, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter,
                        entry.timestamp[:8] if entry.timestamp else "")

        # Level badge
        level = entry.level.upper()
        level_color = self.LEVEL_COLORS.get(level, t.TEXT_SECONDARY)
        badge_font = QFont()
        badge_font.setPixelSize(10)
        badge_font.setWeight(QFont.Weight.Bold)
        painter.setFont(badge_font)
        fm = QFontMetrics(badge_font)
        bw = fm.horizontalAdvance(level) + 12
        bh = 18
        bx = r.x() + ts_w + 4
        by = r.y() + (r.height() - bh) // 2
        painter.setBrush(QColor(level_color + "33"))
        painter.setPen(QColor(level_color))
        painter.drawRoundedRect(bx, by, bw, bh, 9, 9)
        painter.drawText(bx, by, bw, bh, Qt.AlignmentFlag.AlignCenter, level)

        # Source chip
        source = entry.source or ""
        src_color = self.SOURCE_COLORS.get(source.lower(), t.TEXT_MUTED)
        src_bw = fm.horizontalAdvance(source) + 12
        src_bx = bx + bw + 6
        painter.setBrush(QColor(src_color + "22"))
        painter.setPen(QColor(src_color))
        painter.drawRoundedRect(src_bx, by, src_bw, bh, 9, 9)
        painter.drawText(src_bx, by, src_bw, bh, Qt.AlignmentFlag.AlignCenter, source)

        # Message
        body_font = QFont()
        body_font.setPixelSize(12)
        painter.setFont(body_font)
        painter.setPen(QColor(t.TEXT_PRIMARY))
        msg_x = src_bx + src_bw + 10
        msg_rect = r.adjusted(msg_x - r.x(), 0, -8, 0)
        bfm = QFontMetrics(body_font)
        elided = bfm.elidedText(entry.message, Qt.TextElideMode.ElideRight, msg_rect.width())
        painter.drawText(msg_rect, Qt.AlignmentFlag.AlignVCenter, elided)

        # Bottom separator
        painter.setPen(QColor(t.BG_BORDER))
        painter.drawLine(r.x() + 12, r.bottom(), r.right() - 12, r.bottom())

        painter.restore()


class LogsScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._auto_scroll = True
        self._active_levels = {"INFO", "WARNING", "ERROR", "DEBUG", "SUCCESS"}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top bar
        topbar = QWidget()
        topbar.setFixedHeight(56)
        tbl = QHBoxLayout(topbar)
        tbl.setContentsMargins(t.CONTENT_PAD_H, 0, t.CONTENT_PAD_H, 0)
        tbl.setSpacing(t.SP3)

        title = QLabel("Logs")
        title.setStyleSheet(f"color: {t.TEXT_PRIMARY}; font-size: 22px; font-weight: 700; background: transparent;")
        tbl.addWidget(title)
        tbl.addStretch(1)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Buscar...")
        self._search_input.setFixedWidth(220)
        self._search_input.setFixedHeight(32)
        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.timeout.connect(self._apply_search)
        self._search_input.textChanged.connect(lambda: self._search_debounce.start(300))

        auto_cb = QCheckBox("Auto-scroll")
        auto_cb.setChecked(True)
        auto_cb.setStyleSheet(f"color: {t.TEXT_SECONDARY}; background: transparent;")
        auto_cb.stateChanged.connect(lambda s: setattr(self, "_auto_scroll", bool(s)))

        clear_btn = QPushButton("Limpar")
        clear_btn.setFixedHeight(32)
        clear_btn.clicked.connect(self._clear)

        tbl.addWidget(self._search_input)
        tbl.addWidget(auto_cb)
        tbl.addWidget(clear_btn)
        root.addWidget(topbar)

        # Filter row
        filter_row = QWidget()
        filter_row.setFixedHeight(40)
        fl = QHBoxLayout(filter_row)
        fl.setContentsMargins(t.CONTENT_PAD_H, 0, t.CONTENT_PAD_H, 0)
        fl.setSpacing(t.SP2)

        level_lbl = QLabel("Nível:")
        level_lbl.setStyleSheet(f"color: {t.TEXT_MUTED}; font-size: 12px; background: transparent;")
        fl.addWidget(level_lbl)

        self._level_btns: dict[str, QPushButton] = {}
        for level in ["ALL", "INFO", "WARNING", "ERROR", "DEBUG"]:
            btn = QPushButton(level)
            btn.setCheckable(True)
            btn.setChecked(level == "ALL")
            btn.setFixedHeight(26)
            btn.setFixedWidth(70)
            btn.setStyleSheet(self._filter_style(level == "ALL", level))
            btn.clicked.connect(lambda checked, l=level, b=btn: self._on_level_btn(l, b, checked))
            self._level_btns[level] = btn
            fl.addWidget(btn)

        fl.addStretch(1)
        root.addWidget(filter_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {t.BG_BORDER}; border: none;")
        root.addWidget(sep)

        # Log view
        self._model = LogModel(self)
        self._delegate = LogEntryDelegate(self)

        self._view = QListView()
        self._view.setModel(self._model)
        self._view.setItemDelegate(self._delegate)
        self._view.setMouseTracking(True)
        self._view.verticalScrollBar().valueChanged.connect(self._on_scroll)
        root.addWidget(self._view, 1)

        self._state_connected = False
        self._history_loaded = False

        # Retry connecting to qt_app_state (may not be ready at construction)
        self._connect_timer = QTimer(self)
        self._connect_timer.setInterval(250)
        self._connect_timer.timeout.connect(self._connect_state)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._state_connected:
            self._connect_state()
            if not self._state_connected:
                self._connect_timer.start()
        if not self._history_loaded:
            self._load_history()

    def _connect_state(self) -> None:
        try:
            from app.ui.state.qt_app_state import qt_app_state
            if qt_app_state is not None:
                qt_app_state.log_message.connect(self._on_log)
                self._state_connected = True
                self._connect_timer.stop()
        except Exception:
            pass

    def _load_history(self) -> None:
        from app.utils.async_bridge import run_async

        def _done(rows):
            if isinstance(rows, Exception):
                return
            for row in rows:
                # row: (id, level, source, message, created_at)
                _, level, source, message, created_at = row
                ts = (created_at or "")[:8] if created_at else ""
                entry = _LogEntry(ts, level or "INFO", source or "pipeline", message or "")
                self._model.append(entry)
            if self._auto_scroll:
                self._view.scrollToBottom()
            self._history_loaded = True

        async def _fetch():
            from app.core.database import get_logs
            return await get_logs(limit=2000)

        run_async(_fetch(), on_done=_done)

    # ── Level filter ─────────────────────────────────────────────────────────

    def _filter_style(self, active: bool, level: str) -> str:
        color = t.LOG_LEVEL_COLORS.get(level, t.ACCENT) if level != "ALL" else t.ACCENT
        if active:
            return f"""
                QPushButton {{
                    background: {color}33;
                    color: {color};
                    border: 1px solid {color};
                    border-radius: {t.RADIUS_SM}px;
                    font-size: 11px;
                    font-weight: 600;
                }}
            """
        return f"""
            QPushButton {{
                background: {t.BG_ELEVATED};
                color: {t.TEXT_MUTED};
                border: 1px solid {t.BG_BORDER};
                border-radius: {t.RADIUS_SM}px;
                font-size: 11px;
            }}
            QPushButton:hover {{ color: {t.TEXT_PRIMARY}; }}
        """

    def _on_level_btn(self, level: str, btn: QPushButton, checked: bool) -> None:
        btn.setStyleSheet(self._filter_style(checked, level))
        if level == "ALL":
            if checked:
                self._active_levels = {"INFO", "WARNING", "ERROR", "DEBUG", "SUCCESS"}
        else:
            if checked:
                self._active_levels.add(level)
            else:
                self._active_levels.discard(level)
        self._model.set_level_filter(self._active_levels)

    def _apply_search(self) -> None:
        self._model.set_search(self._search_input.text())

    def _on_scroll(self, value: int) -> None:
        sb = self._view.verticalScrollBar()
        if value < sb.maximum() - 50:
            self._auto_scroll = False

    def _on_log(self, message: str, level: str, source: str = "pipeline") -> None:
        import datetime
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        entry = _LogEntry(ts, level.upper(), source, message)
        self._model.append(entry)
        if self._auto_scroll:
            self._view.scrollToBottom()

    def _clear(self) -> None:
        self._model.beginResetModel()
        self._model._entries.clear()
        self._model._visible.clear()
        self._model.endResetModel()
        from app.utils.async_bridge import run_async

        async def _do_clear():
            from app.core.database import clear_logs
            await clear_logs()

        run_async(_do_clear())
