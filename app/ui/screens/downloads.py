"""Downloads screen — active torrent list via qBittorrent."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, QAbstractListModel, QModelIndex, QSize
from PySide6.QtGui import QColor, QPainter, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListView,
    QFrame, QStyledItemDelegate, QStyleOptionViewItem,
)

from app.ui.design import tokens as t
from app.utils.async_bridge import run_async


class _TorrentModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._torrents: list[dict] = []

    def set_torrents(self, torrents: list[dict]) -> None:
        self.beginResetModel()
        self._torrents = torrents
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._torrents)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        t_data = self._torrents[index.row()]
        if role == Qt.ItemDataRole.UserRole:
            return t_data
        return None


class _TorrentDelegate(QStyledItemDelegate):
    ROW_H = 72

    def sizeHint(self, option, index) -> QSize:
        return QSize(option.rect.width(), self.ROW_H)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        painter.save()
        data = index.data(Qt.ItemDataRole.UserRole)
        if data is None:
            painter.restore()
            return

        r = option.rect

        # Background
        bg = QColor(t.BG_ELEVATED) if option.state & __import__(
            "PySide6.QtWidgets", fromlist=["QStyle"]
        ).QStyle.StateFlag.State_MouseOver else QColor(t.BG_SURFACE)
        painter.fillRect(r, bg)

        # Bottom separator
        painter.setPen(QColor(t.BG_BORDER))
        painter.drawLine(r.x() + 16, r.bottom(), r.right() - 16, r.bottom())

        name = data.get("name", "Unknown")
        progress = float(data.get("progress", 0))
        state = data.get("state", "unknown")
        dlspeed = data.get("dlspeed", 0)
        eta = data.get("eta", -1)
        size = data.get("total_size", 0)

        # Name
        font = QFont()
        font.setPixelSize(13)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(QColor(t.TEXT_PRIMARY))
        painter.drawText(
            r.adjusted(16, 8, -120, -40),
            Qt.AlignmentFlag.AlignVCenter,
            painter.fontMetrics().elidedText(name, Qt.TextElideMode.ElideRight, r.width() - 136),
        )

        # Progress bar
        bar_y = r.y() + 38
        bar_h = 4
        bar_x = r.x() + 16
        bar_w = r.width() - 32

        painter.setBrush(QColor(t.BG_BORDER))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, 2, 2)

        filled = int(bar_w * progress)
        if filled > 0:
            if state in ("downloading", "stalledDL"):
                fill_color = QColor(t.DOWNLOADING)
            elif state in ("uploading", "seeding", "stalledUP"):
                fill_color = QColor(t.SUCCESS)
            else:
                fill_color = QColor(t.TEXT_MUTED)
            painter.setBrush(fill_color)
            painter.drawRoundedRect(bar_x, bar_y, filled, bar_h, 2, 2)

        # Meta info
        font2 = QFont()
        font2.setPixelSize(11)
        painter.setFont(font2)
        painter.setPen(QColor(t.TEXT_MUTED))

        pct = f"{progress * 100:.1f}%"
        speed = f"{dlspeed / 1024 / 1024:.1f} MB/s" if dlspeed > 0 else ""
        eta_str = _format_eta(eta)
        size_str = _format_size(size)

        meta_parts = [pct, size_str]
        if speed:
            meta_parts.append(speed)
        if eta_str:
            meta_parts.append(f"ETA {eta_str}")

        meta_text = "  ·  ".join(meta_parts)
        painter.drawText(
            r.adjusted(16, 48, -120, -4),
            Qt.AlignmentFlag.AlignVCenter,
            meta_text,
        )

        # State chip
        state_text, state_color = _state_display(state)
        font3 = QFont()
        font3.setPixelSize(11)
        font3.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font3)
        painter.setPen(QColor(state_color))
        painter.drawText(
            r.adjusted(r.width() - 110, 0, -8, 0),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
            state_text,
        )

        painter.restore()


def _format_eta(seconds: int) -> str:
    if seconds < 0 or seconds > 86400 * 7:
        return ""
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def _format_size(size: int) -> str:
    if size > 1024 ** 3:
        return f"{size / 1024 ** 3:.1f} GB"
    if size > 1024 ** 2:
        return f"{size / 1024 ** 2:.0f} MB"
    return f"{size / 1024:.0f} KB"


def _state_display(state: str) -> tuple[str, str]:
    map_ = {
        "downloading": ("Baixando", t.DOWNLOADING),
        "stalledDL":   ("Parado", t.WARNING),
        "uploading":   ("Enviando", t.SUCCESS),
        "seeding":     ("Seeding", t.SUCCESS),
        "stalledUP":   ("Seeding", t.SUCCESS),
        "pausedDL":    ("Pausado", t.TEXT_MUTED),
        "pausedUP":    ("Pausado", t.TEXT_MUTED),
        "error":       ("Erro", t.ERROR),
        "checkingDL":  ("Verificando", t.INFO),
        "queuedDL":    ("Na Fila", t.INFO),
    }
    return map_.get(state, (state.capitalize(), t.TEXT_SECONDARY))


class DownloadsScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top bar
        topbar = QWidget()
        topbar.setFixedHeight(56)
        tbl = QHBoxLayout(topbar)
        tbl.setContentsMargins(t.CONTENT_PAD_H, 0, t.CONTENT_PAD_H, 0)

        title = QLabel("Downloads")
        title.setStyleSheet(f"color: {t.TEXT_PRIMARY}; font-size: 22px; font-weight: 700; background: transparent;")
        tbl.addWidget(title)
        tbl.addStretch(1)

        self._status_dot = QLabel("● Desconectado")
        self._status_dot.setStyleSheet(f"color: {t.TEXT_MUTED}; font-size: 12px; background: transparent;")
        tbl.addWidget(self._status_dot)
        root.addWidget(topbar)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {t.BG_BORDER}; border: none;")
        root.addWidget(sep)

        self._model = _TorrentModel(self)
        self._view = QListView()
        self._view.setModel(self._model)
        self._view.setItemDelegate(_TorrentDelegate(self._view))
        self._view.setSpacing(0)
        root.addWidget(self._view, 1)

        self._empty = QLabel("Nenhum download ativo.\nO Anime Monitor adicionará torrents automaticamente.")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setStyleSheet(f"color: {t.TEXT_MUTED}; font-size: 14px; background: transparent;")
        self._empty.hide()
        root.addWidget(self._empty)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(5000)

        QTimer.singleShot(0, self._poll)

    def _poll(self) -> None:
        run_async(self._fetch(), on_done=self._on_data)

    async def _fetch(self):
        try:
            from app.providers.torrents.qbittorrent import QBittorrentProvider
            from app.core.config import get_qbittorrent_config
            cfg = get_qbittorrent_config()
            provider = QBittorrentProvider(
                host=cfg["host"], port=cfg["port"],
                username=cfg["username"], password=cfg["password"],
            )
            torrents = await provider.get_all_torrents()
            return {"connected": True, "torrents": torrents or []}
        except Exception as e:
            return {"connected": False, "torrents": [], "error": str(e)}

    def _on_data(self, result) -> None:
        if isinstance(result, Exception):
            self._status_dot.setText("● Erro de conexão")
            self._status_dot.setStyleSheet(f"color: {t.ERROR}; font-size: 12px; background: transparent;")
            return

        connected = result.get("connected", False)
        torrents = result.get("torrents", [])

        if connected:
            self._status_dot.setText("● Conectado")
            self._status_dot.setStyleSheet(f"color: {t.SUCCESS}; font-size: 12px; background: transparent;")
        else:
            self._status_dot.setText("● Desconectado")
            self._status_dot.setStyleSheet(f"color: {t.TEXT_MUTED}; font-size: 12px; background: transparent;")

        if torrents:
            self._empty.hide()
            self._view.show()
            self._model.set_torrents(torrents)
        else:
            self._view.hide()
            self._empty.show()

    def showEvent(self, event):
        super().showEvent(event)
        self._poll()
