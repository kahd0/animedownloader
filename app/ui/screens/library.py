"""Library screen — sortable table view of all monitored anime."""
from __future__ import annotations

from PySide6.QtCore import (
    Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel,
    QTimer, Signal,
)
from PySide6.QtGui import QColor, QPixmap, QPainter, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableView, QHeaderView,
    QLabel, QPushButton, QLineEdit, QMenu, QStyledItemDelegate,
    QStyleOptionViewItem, QFrame, QSizePolicy, QAbstractItemView,
)

from app.ui.design import tokens as t
from app.utils.async_bridge import run_async
from app.ui.utils.image_cache import get_cover_pixmap_sync

import os


class _AnimeTableModel(QAbstractTableModel):
    HEADERS = ["", "Título", "Episódio", "Status", "Resolução", "Atualizado", ""]
    COL_THUMB = 0
    COL_TITLE = 1
    COL_EP    = 2
    COL_STATUS= 3
    COL_RES   = 4
    COL_DATE  = 5
    COL_ACTS  = 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: list[tuple] = []

    def set_data(self, rows: list[tuple]) -> None:
        self.beginResetModel()
        self._data = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._data)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]
        return None

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._data):
            return None
        row = self._data[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == self.COL_TITLE:
                return row[6] or row[1]  # official_title or title_pattern
            if col == self.COL_EP:
                return f"EP {row[2]:02d}" if row[2] else "—"
            if col == self.COL_STATUS:
                airing = row[7] or ""
                if "Airing" in airing:
                    return "Em Exibição"
                elif "Finished" in airing:
                    return "Finalizado"
                return airing or "—"
            if col == self.COL_RES:
                return row[3] or "—"
            if col == self.COL_DATE:
                return row[4] or "—"
            return None

        if role == Qt.ItemDataRole.UserRole:
            return row  # full tuple

        if role == Qt.ItemDataRole.UserRole + 1:  # has_new
            return bool(row[8])

        return None

    def get_row(self, index: int) -> tuple | None:
        if 0 <= index < len(self._data):
            return self._data[index]
        return None


class _LibraryDelegate(QStyledItemDelegate):
    """Paints thumbnail, status chip, and action buttons."""

    ROW_HEIGHT = 64

    def sizeHint(self, option, index):
        return __import__("PySide6.QtCore", fromlist=["QSize"]).QSize(option.rect.width(), self.ROW_HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        painter.save()
        row_data = index.data(Qt.ItemDataRole.UserRole)
        col = index.column()

        # Row background
        if option.state & __import__("PySide6.QtWidgets", fromlist=["QStyle"]).QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QColor(t.BG_ELEVATED))
        elif option.state & __import__("PySide6.QtWidgets", fromlist=["QStyle"]).QStyle.StateFlag.State_MouseOver:
            painter.fillRect(option.rect, QColor(t.BG_ELEVATED))
        else:
            painter.fillRect(option.rect, QColor(t.BG_DEEP))

        if row_data is None:
            painter.restore()
            return

        r = option.rect

        if col == _AnimeTableModel.COL_THUMB:
            # Thumbnail
            thumb_w, thumb_h = 40, 56
            tx = r.x() + (r.width() - thumb_w) // 2
            ty = r.y() + (r.height() - thumb_h) // 2

            cover_path = _find_cover(row_data[1])
            if cover_path:
                px = get_cover_pixmap_sync(cover_path, thumb_w, thumb_h)
                if px and not px.isNull():
                    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                    painter.drawPixmap(tx, ty, thumb_w, thumb_h, px)
                    painter.restore()
                    return

            # Placeholder
            painter.setBrush(QColor(t.BG_ELEVATED))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(tx, ty, thumb_w, thumb_h, 4, 4)

        elif col == _AnimeTableModel.COL_STATUS:
            status_text = index.data(Qt.ItemDataRole.DisplayRole) or ""
            if "Exibição" in status_text:
                color = t.SUCCESS
            elif "Finalizado" in status_text:
                color = t.TEXT_MUTED
            else:
                color = t.TEXT_SECONDARY

            # Chip
            font = QFont()
            font.setPixelSize(11)
            font.setWeight(QFont.Weight.DemiBold)
            painter.setFont(font)
            fm = painter.fontMetrics()
            tw = fm.horizontalAdvance(status_text)
            ch = 22
            cw = tw + 16
            cx = r.x() + 8
            cy = r.y() + (r.height() - ch) // 2

            painter.setBrush(QColor(color + "33"))
            painter.setPen(QColor(color))
            painter.drawRoundedRect(cx, cy, cw, ch, 11, 11)
            painter.drawText(cx, cy, cw, ch, Qt.AlignmentFlag.AlignCenter, status_text)

        elif col in (
            _AnimeTableModel.COL_TITLE,
            _AnimeTableModel.COL_EP,
            _AnimeTableModel.COL_RES,
            _AnimeTableModel.COL_DATE,
        ):
            text = index.data(Qt.ItemDataRole.DisplayRole) or ""
            font = QFont()
            font.setPixelSize(13)
            if col == _AnimeTableModel.COL_TITLE:
                font.setWeight(QFont.Weight.DemiBold)
            painter.setFont(font)
            color = t.TEXT_PRIMARY if col == _AnimeTableModel.COL_TITLE else t.TEXT_SECONDARY
            painter.setPen(QColor(color))
            text_rect = r.adjusted(8, 0, -8, 0)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                           painter.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, text_rect.width()))

        painter.restore()


def _find_cover(title_pattern: str) -> str | None:
    try:
        from app.core.config import COVERS_DIR as COVER_DIR
        safe = title_pattern.replace("/", "_").replace("\\", "_")
        for ext in (".jpg", ".png", ".jpeg", ".webp"):
            path = os.path.join(COVER_DIR, safe + ext)
            if os.path.exists(path):
                return path
    except Exception:
        pass
    return None


class LibraryScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_data: list[tuple] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top bar
        topbar = QWidget()
        topbar.setFixedHeight(56)
        tbl = QHBoxLayout(topbar)
        tbl.setContentsMargins(t.CONTENT_PAD_H, 0, t.CONTENT_PAD_H, 0)
        tbl.setSpacing(t.SP3)

        title = QLabel("Monitorados")
        title.setStyleSheet(f"color: {t.TEXT_PRIMARY}; font-size: 22px; font-weight: 700; background: transparent;")
        tbl.addWidget(title)
        tbl.addStretch(1)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Buscar...")
        self._search.setFixedWidth(260)
        self._search.setFixedHeight(34)
        self._search.textChanged.connect(self._on_search)
        tbl.addWidget(self._search)

        root.addWidget(topbar)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {t.BG_BORDER}; border: none;")
        root.addWidget(sep)

        # Table
        self._model = _AnimeTableModel(self)
        self._proxy = QSortFilterProxyModel(self)
        self._proxy.setSourceModel(self._model)
        self._proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._proxy.setFilterKeyColumn(_AnimeTableModel.COL_TITLE)

        self._table = QTableView()
        self._table.setModel(self._proxy)
        self._table.setItemDelegate(_LibraryDelegate(self._table))
        self._table.setShowGrid(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setMouseTracking(True)
        self._table.setSortingEnabled(True)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(
            _AnimeTableModel.COL_THUMB, QHeaderView.ResizeMode.Fixed)
        self._table.horizontalHeader().setSectionResizeMode(
            _AnimeTableModel.COL_TITLE, QHeaderView.ResizeMode.Stretch)
        self._table.setColumnWidth(_AnimeTableModel.COL_THUMB, 64)
        self._table.setColumnWidth(_AnimeTableModel.COL_EP, 80)
        self._table.setColumnWidth(_AnimeTableModel.COL_STATUS, 130)
        self._table.setColumnWidth(_AnimeTableModel.COL_RES, 70)
        self._table.setColumnWidth(_AnimeTableModel.COL_DATE, 120)
        self._table.setColumnWidth(_AnimeTableModel.COL_ACTS, 50)
        self._table.verticalHeader().setDefaultSectionSize(_LibraryDelegate.ROW_HEIGHT)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)

        root.addWidget(self._table, 1)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(lambda: self._proxy.setFilterFixedString(self._search.text()))

        QTimer.singleShot(0, self.refresh)

    def refresh(self) -> None:
        run_async(self._fetch(), on_done=self._on_data)

    async def _fetch(self):
        from app.core.database import get_monitored_animes
        return await get_monitored_animes()

    def _on_data(self, result) -> None:
        if isinstance(result, Exception):
            return
        self._all_data = result or []
        self._model.set_data(self._all_data)

    def _on_search(self) -> None:
        self._debounce.start(300)

    def _show_context_menu(self, pos) -> None:
        idx = self._table.indexAt(pos)
        if not idx.isValid():
            return
        src_idx = self._proxy.mapToSource(idx)
        row = self._model.get_row(src_idx.row())
        if not row:
            return

        menu = QMenu(self)
        menu.addAction("▶  Assistir", lambda: self._action_play(row))
        menu.addAction("✓  Marcar como visto", lambda: self._action_watched(row))
        menu.addSeparator()
        menu.addAction("🔍  Buscar legenda", lambda: self._action_subtitle(row))
        menu.addAction("🌐  Traduzir legenda", lambda: self._action_translate(row))
        menu.addSeparator()
        menu.addAction("📁  Abrir pasta", lambda: self._action_folder(row))
        menu.addAction("✏  Editar episódio", lambda: self._action_edit(row))
        menu.addSeparator()
        menu.addAction("🗑  Remover", lambda: self._action_remove(row))
        menu.exec(self._table.viewport().mapToGlobal(pos))

    # ── Row: id(0) title_pattern(1) last_episode(2) resolution(3) last_download_date(4)
    #          cover_url(5) official_title(6) airing_status(7) has_new_episode(8) last_downloaded(9)

    def _action_play(self, row) -> None:
        import subprocess
        from app.core.config import get_final_dir
        final_dir = get_final_dir()
        pattern = row[1].replace("/", "_").lower()
        try:
            files = [
                f for f in os.listdir(final_dir)
                if pattern in f.lower() and f.lower().endswith((".mkv", ".mp4", ".avi", ".m4v"))
            ]
        except OSError:
            files = []
        if not files:
            self._toast("Nenhum arquivo de vídeo encontrado", "error")
            return
        files.sort()
        if len(files) == 1:
            subprocess.Popen(["xdg-open", os.path.join(final_dir, files[0])])
        else:
            self._pick_and_play(final_dir, files)

    def _pick_and_play(self, final_dir: str, files: list[str]) -> None:
        import subprocess
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QListWidget
        dlg = QDialog(self)
        dlg.setWindowTitle("Selecionar episódio")
        dlg.resize(500, 360)
        lay = QVBoxLayout(dlg)
        lst = QListWidget(dlg)
        lst.addItems(sorted(files, reverse=True))
        lay.addWidget(lst)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        lst.doubleClicked.connect(dlg.accept)
        if dlg.exec() == QDialog.DialogCode.Accepted and lst.currentItem():
            subprocess.Popen(["xdg-open", os.path.join(final_dir, lst.currentItem().text())])

    def _action_watched(self, row) -> None:
        from PySide6.QtWidgets import (
            QDialog, QDialogButtonBox, QSpinBox, QFormLayout,
        )
        anime_id = row[0]
        name = row[6] or row[1]
        current_ep = row[2] or 0

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Marcar como visto — {name}")
        dlg.resize(340, 140)
        lay = QVBoxLayout(dlg)

        form = QFormLayout()
        spin = QSpinBox()
        spin.setRange(0, 99999)
        spin.setValue(current_ep)
        form.addRow("Último episódio assistido:", spin)
        lay.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_ep = spin.value()
            from app.core.database import set_last_episode
            run_async(set_last_episode(anime_id, new_ep), on_done=lambda _: self.refresh())
            self._toast(f"EP {new_ep:02d} marcado para {name}", "success")

    def _action_subtitle(self, row) -> None:
        anime_id = row[0]
        name = row[6] or row[1]
        from app.core.jobs.queue import job_queue
        run_async(
            job_queue.enqueue("subtitle", anime_id=anime_id),
            on_done=lambda r: self._toast(
                f"Busca de legenda enfileirada — {name}" if not isinstance(r, Exception)
                else f"Erro ao enfileirar: {r}", "info" if not isinstance(r, Exception) else "error"
            ),
        )

    def _action_translate(self, row) -> None:
        anime_id = row[0]
        name = row[6] or row[1]
        from app.core.jobs.queue import job_queue
        run_async(
            job_queue.enqueue("translation", anime_id=anime_id),
            on_done=lambda r: self._toast(
                f"Tradução enfileirada — {name}" if not isinstance(r, Exception)
                else f"Erro ao enfileirar: {r}", "info" if not isinstance(r, Exception) else "error"
            ),
        )

    def _action_folder(self, row) -> None:
        import subprocess
        from app.core.config import get_final_dir
        folder = os.path.join(get_final_dir(), row[1].replace("/", "_"))
        if os.path.isdir(folder):
            subprocess.Popen(["xdg-open", folder])
        else:
            self._toast("Pasta não encontrada", "error")

    def _action_edit(self, row) -> None:
        from PySide6.QtWidgets import (
            QDialog, QDialogButtonBox, QSpinBox, QFormLayout,
        )
        anime_id = row[0]
        name = row[6] or row[1]
        current_ep = row[2] or 0

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Editar episódio — {name}")
        dlg.resize(340, 140)
        lay = QVBoxLayout(dlg)

        form = QFormLayout()
        spin = QSpinBox()
        spin.setRange(0, 99999)
        spin.setValue(current_ep)
        form.addRow("Último episódio:", spin)
        lay.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_ep = spin.value()
            from app.core.database import set_last_episode
            run_async(set_last_episode(anime_id, new_ep), on_done=lambda _: self.refresh())
            self._toast(f"Episódio atualizado: {current_ep} → {new_ep}", "success")

    def _action_remove(self, row) -> None:
        from PySide6.QtWidgets import QMessageBox
        anime_id = row[0]
        name = row[6] or row[1]
        reply = QMessageBox.question(
            self,
            "Remover anime",
            f"Remover «{name}» do monitoramento?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Yes:
            from app.core.database import remove_anime
            run_async(remove_anime(anime_id), on_done=lambda _: self.refresh())
            self._toast(f"{name} removido", "info")

    def _toast(self, message: str, kind: str = "info") -> None:
        try:
            from app.ui.components.toast import ToastManager
            ToastManager.instance().show(message, kind)
        except Exception:
            pass

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
