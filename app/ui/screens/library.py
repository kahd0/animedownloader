"""Library screen — sortable table view of all monitored anime."""
from __future__ import annotations

import os
import re

from PySide6.QtCore import (
    Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel,
    QTimer, Signal,
)
from PySide6.QtGui import QColor, QPainter, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableView, QHeaderView,
    QLabel, QPushButton, QLineEdit, QMenu, QStyledItemDelegate,
    QStyleOptionViewItem, QFrame, QAbstractItemView,
)

from app.ui.design import tokens as t
from app.utils.async_bridge import run_async
from app.ui.utils.image_cache import get_cover_pixmap_sync

# Row index constants — must match SELECT order in get_monitored_animes()
_ID          = 0
_PATTERN     = 1
_LAST_EP     = 2
_RES         = 3
_DL_DATE     = 4
_COVER_URL   = 5
_TITLE       = 6
_STATUS      = 7
_HAS_NEW     = 8
_LAST_DL     = 9
_TOTAL_EPS   = 10
_SCORE       = 11
_STUDIO      = 12
_SEASON      = 13
_YEAR        = 14
_SYNOPSIS    = 15
_LAST_READY  = 16


def _find_cover(title_pattern: str) -> str | None:
    try:
        from app.core.config import COVERS_DIR as COVER_DIR
        safe = re.sub(r'[^\w\s-]', '', title_pattern).strip().lower().replace(' ', '_')
        for ext in (".jpg", ".png", ".jpeg", ".webp"):
            path = os.path.join(COVER_DIR, safe + ext)
            if os.path.exists(path):
                return path
    except Exception:
        pass
    return None


class _AnimeTableModel(QAbstractTableModel):
    HEADERS = ["", "Título", "Progresso", "Status", "Score", "Estúdio", "Atualizado"]

    COL_THUMB  = 0
    COL_TITLE  = 1
    COL_PROG   = 2
    COL_STATUS = 3
    COL_SCORE  = 4
    COL_STUDIO = 5
    COL_DATE   = 6

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
                return row[_TITLE] or row[_PATTERN]
            if col == self.COL_PROG:
                ep = row[_LAST_EP] or 0
                total = row[_TOTAL_EPS]
                if total:
                    return f"EP {ep:02d} / {total:02d}"
                return f"EP {ep:02d}" if ep else "—"
            if col == self.COL_STATUS:
                return _status_label(row[_STATUS])
            if col == self.COL_SCORE:
                s = row[_SCORE]
                return f"★ {s:.1f}" if s else "—"
            if col == self.COL_STUDIO:
                return row[_STUDIO] or "—"
            if col == self.COL_DATE:
                return row[_DL_DATE] or "—"
            return None

        if role == Qt.ItemDataRole.UserRole:
            return row

        if role == Qt.ItemDataRole.UserRole + 1:  # has_new
            return bool(row[_HAS_NEW])

        return None

    def get_row(self, index: int) -> tuple | None:
        if 0 <= index < len(self._data):
            return self._data[index]
        return None


def _status_label(raw: str | None) -> str:
    if not raw:
        return "—"
    if "Airing" in raw:
        return "Em Exibição"
    if "Finished" in raw:
        return "Finalizado"
    if "Not yet" in raw:
        return "Em Breve"
    return raw


def _status_color(raw: str | None) -> str:
    if not raw:
        return t.TEXT_MUTED
    if "Airing" in raw:
        return t.SUCCESS
    if "Finished" in raw:
        return t.TEXT_MUTED
    if "Not yet" in raw:
        return t.ACCENT
    return t.TEXT_SECONDARY


class _LibraryDelegate(QStyledItemDelegate):
    ROW_HEIGHT = 68

    def sizeHint(self, option, index):
        from PySide6.QtCore import QSize
        return QSize(option.rect.width(), self.ROW_HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        from PySide6.QtWidgets import QStyle
        painter.save()
        row_data = index.data(Qt.ItemDataRole.UserRole)
        has_new  = index.data(Qt.ItemDataRole.UserRole + 1)
        col = index.column()

        selected  = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered   = bool(option.state & QStyle.StateFlag.State_MouseOver)

        bg = t.BG_ELEVATED if (selected or hovered) else t.BG_DEEP
        painter.fillRect(option.rect, QColor(bg))

        if row_data is None:
            painter.restore()
            return

        r = option.rect

        if col == _AnimeTableModel.COL_THUMB:
            thumb_w, thumb_h = 42, 58
            tx = r.x() + (r.width() - thumb_w) // 2
            ty = r.y() + (r.height() - thumb_h) // 2

            cover_path = _find_cover(row_data[_PATTERN])
            if cover_path:
                px = get_cover_pixmap_sync(cover_path, thumb_w, thumb_h)
                if px and not px.isNull():
                    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                    from PySide6.QtCore import QRect
                    painter.drawPixmap(QRect(tx, ty, thumb_w, thumb_h), px)
                    # "Novo" badge
                    if has_new:
                        _draw_badge(painter, tx + thumb_w - 10, ty - 4, t.ACCENT)
                    painter.restore()
                    return

            # Placeholder rect
            painter.setBrush(QColor(t.BG_ELEVATED))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(tx, ty, thumb_w, thumb_h, 4, 4)
            if has_new:
                _draw_badge(painter, tx + thumb_w - 10, ty - 4, t.ACCENT)

        elif col == _AnimeTableModel.COL_STATUS:
            status_raw  = row_data[_STATUS]
            status_text = _status_label(status_raw)
            color       = _status_color(status_raw)

            font = QFont()
            font.setPixelSize(11)
            font.setWeight(QFont.Weight.DemiBold)
            painter.setFont(font)
            fm  = painter.fontMetrics()
            tw  = fm.horizontalAdvance(status_text)
            ch, cw = 22, tw + 16
            cx = r.x() + 8
            cy = r.y() + (r.height() - ch) // 2

            painter.setBrush(QColor(color + "33"))
            painter.setPen(QColor(color))
            painter.drawRoundedRect(cx, cy, cw, ch, 11, 11)
            painter.drawText(cx, cy, cw, ch, Qt.AlignmentFlag.AlignCenter, status_text)

        elif col == _AnimeTableModel.COL_SCORE:
            text = index.data(Qt.ItemDataRole.DisplayRole) or ""
            font = QFont()
            font.setPixelSize(12)
            font.setWeight(QFont.Weight.DemiBold)
            painter.setFont(font)
            score_val = row_data[_SCORE]
            color = (t.SUCCESS if score_val and score_val >= 8
                     else t.ACCENT if score_val and score_val >= 7
                     else t.TEXT_SECONDARY)
            painter.setPen(QColor(color))
            painter.drawText(r.adjusted(8, 0, -8, 0),
                             Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)

        elif col in (
            _AnimeTableModel.COL_TITLE,
            _AnimeTableModel.COL_PROG,
            _AnimeTableModel.COL_STUDIO,
            _AnimeTableModel.COL_DATE,
        ):
            text = index.data(Qt.ItemDataRole.DisplayRole) or ""
            font = QFont()
            font.setPixelSize(13)
            if col == _AnimeTableModel.COL_TITLE:
                font.setWeight(QFont.Weight.DemiBold)
                color = t.TEXT_PRIMARY
                # draw "NOVO" pill next to title when has_new
                if has_new:
                    badge_font = QFont()
                    badge_font.setPixelSize(9)
                    badge_font.setWeight(QFont.Weight.Bold)
                    painter.setFont(badge_font)
                    bfm = painter.fontMetrics()
                    bw = bfm.horizontalAdvance("NOVO") + 8
                    bh = 14
                    bx = r.x() + 8
                    by = r.y() + (r.height() - bh) // 2 - 10
                    painter.setBrush(QColor(t.ACCENT + "33"))
                    painter.setPen(QColor(t.ACCENT))
                    painter.drawRoundedRect(bx, by, bw, bh, 7, 7)
                    painter.drawText(bx, by, bw, bh, Qt.AlignmentFlag.AlignCenter, "NOVO")
                    # shift main text down
                    text_rect = r.adjusted(8, 6, -8, 0)
                    painter.setFont(font)
                    painter.setPen(QColor(color))
                    painter.drawText(text_rect,
                                     Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                                     painter.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, text_rect.width()))
                    painter.restore()
                    return
            else:
                color = t.TEXT_SECONDARY

            painter.setFont(font)
            painter.setPen(QColor(color))
            text_rect = r.adjusted(8, 0, -8, 0)
            painter.drawText(text_rect,
                             Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                             painter.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, text_rect.width()))

        painter.restore()


def _draw_badge(painter: QPainter, cx: int, cy: int, color: str) -> None:
    painter.setBrush(QColor(color))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(cx - 5, cy, 10, 10)


class LibraryScreen(QWidget):
    check_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._all_data: list[tuple] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Top bar ──────────────────────────────────────────────────────────
        topbar = QWidget()
        topbar.setFixedHeight(56)
        tbl = QHBoxLayout(topbar)
        tbl.setContentsMargins(t.CONTENT_PAD_H, 0, t.CONTENT_PAD_H, 0)
        tbl.setSpacing(t.SP3)

        title_lbl = QLabel("Monitorados")
        title_lbl.setStyleSheet(
            f"color: {t.TEXT_PRIMARY}; font-size: 22px; font-weight: 700; background: transparent;"
        )
        tbl.addWidget(title_lbl)
        tbl.addStretch(1)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Buscar...")
        self._search.setFixedWidth(240)
        self._search.setFixedHeight(34)
        self._search.textChanged.connect(self._on_search)
        tbl.addWidget(self._search)

        self._count_lbl = QLabel("")
        self._count_lbl.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: 12px; background: transparent;"
        )
        tbl.addWidget(self._count_lbl)


        self._check_btn = QPushButton("⟳  Verificar agora")
        self._check_btn.setFixedHeight(34)
        self._check_btn.setStyleSheet(f"""
            QPushButton {{
                background: {t.ACCENT_MUTED};
                color: {t.ACCENT};
                border: 1px solid {t.ACCENT};
                border-radius: {t.RADIUS_2XL}px;
                padding: 0 14px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background: {t.ACCENT}; color: #fff; }}
            QPushButton:disabled {{ opacity: 0.5; }}
        """)
        self._check_btn.clicked.connect(self._on_check_now)
        tbl.addWidget(self._check_btn)

        self._organize_btn = QPushButton("⊡  Organizar agora")
        self._organize_btn.setFixedHeight(34)
        self._organize_btn.setStyleSheet(f"""
            QPushButton {{
                background: {t.BG_ELEVATED};
                color: {t.TEXT_SECONDARY};
                border: 1px solid {t.BG_BORDER};
                border-radius: {t.RADIUS_2XL}px;
                padding: 0 14px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background: {t.BG_BORDER}; color: {t.TEXT_PRIMARY}; }}
            QPushButton:disabled {{ opacity: 0.5; }}
        """)
        self._organize_btn.clicked.connect(self._on_organize_now)
        tbl.addWidget(self._organize_btn)

        root.addWidget(topbar)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {t.BG_BORDER}; border: none;")
        root.addWidget(sep)

        # ── Body: full-width table ─────────────────────────────────────────────
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
        self._table.verticalHeader().setDefaultSectionSize(_LibraryDelegate.ROW_HEIGHT)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)
        self._table.doubleClicked.connect(self._on_row_double_clicked)

        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(_AnimeTableModel.COL_THUMB,  QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(_AnimeTableModel.COL_TITLE,  QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(_AnimeTableModel.COL_PROG,   QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(_AnimeTableModel.COL_STATUS, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(_AnimeTableModel.COL_SCORE,  QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(_AnimeTableModel.COL_STUDIO, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(_AnimeTableModel.COL_DATE,   QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(_AnimeTableModel.COL_THUMB,  68)
        self._table.setColumnWidth(_AnimeTableModel.COL_PROG,   110)
        self._table.setColumnWidth(_AnimeTableModel.COL_STATUS, 130)
        self._table.setColumnWidth(_AnimeTableModel.COL_SCORE,  72)
        self._table.setColumnWidth(_AnimeTableModel.COL_STUDIO, 150)
        self._table.setColumnWidth(_AnimeTableModel.COL_DATE,   120)

        root.addWidget(self._table, 1)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(lambda: self._proxy.setFilterFixedString(self._search.text()))

        QTimer.singleShot(0, self.refresh)

    # ── Data ─────────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        run_async(self._fetch(), on_done=self._on_data)

    async def _fetch(self):
        from app.core.database import get_monitored_animes
        return await get_monitored_animes()

    def _on_data(self, result) -> None:
        if isinstance(result, Exception):
            return
        self._all_data = result or []
        self._apply_filter()

    def _apply_filter(self) -> None:
        self._model.set_data(self._all_data)
        self._count_lbl.setText(f"{len(self._all_data)} monitorado(s)")

    def _on_search(self) -> None:
        self._debounce.start(300)

    def _on_row_double_clicked(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        src = self._proxy.mapToSource(index)
        row = self._model.get_row(src.row())
        if row:
            from app.ui.components.detail_panel import DetailPanel
            DetailPanel(row, self.window()).exec()
            self.refresh()

    # ── Check now ────────────────────────────────────────────────────────────

    def _on_check_now(self) -> None:
        self._check_btn.setEnabled(False)
        self._check_btn.setText("Verificando…")
        self.check_requested.emit()
        run_async(self._do_check(), on_done=self._on_check_done)

    async def _do_check(self):
        from app.core.downloader import check_for_updates
        return await check_for_updates()

    def _on_check_done(self, result) -> None:
        self._check_btn.setEnabled(True)
        self._check_btn.setText("⟳  Verificar agora")
        if isinstance(result, Exception):
            self._toast(f"Erro na verificação: {result}", "error")
            return
        triggered = result or []
        if triggered:
            self._toast(f"{len(triggered)} novo(s) episódio(s) encontrado(s)", "success")
        else:
            self._toast("Nenhum episódio novo encontrado", "info")
        self.refresh()

    # ── Organize now ──────────────────────────────────────────────────────────

    def _on_organize_now(self) -> None:
        self._organize_btn.setEnabled(False)
        self._organize_btn.setText("Organizando…")
        run_async(self._do_organize(), on_done=self._on_organize_done)

    async def _do_organize(self):
        from app.core.downloader import organize_downloads
        return await organize_downloads()

    def _on_organize_done(self, result) -> None:
        self._organize_btn.setEnabled(True)
        self._organize_btn.setText("⊡  Organizar agora")
        if isinstance(result, Exception):
            self._toast(f"Erro ao organizar: {result}", "error")
            return
        moved = result or []
        if moved:
            self._toast(f"{len(moved)} arquivo(s) organizado(s)", "success")
        else:
            self._toast("Nenhum arquivo novo para organizar", "info")
        self.refresh()

    # ── Context menu ─────────────────────────────────────────────────────────

    def _show_context_menu(self, pos) -> None:
        idx = self._table.indexAt(pos)
        if not idx.isValid():
            return
        src_idx = self._proxy.mapToSource(idx)
        row = self._model.get_row(src_idx.row())
        if not row:
            return

        menu = QMenu(self)
        menu.addAction("▶  Assistir",            lambda: self._action_play(row))
        menu.addAction("✓  Marcar como visto",    lambda: self._action_watched(row))
        menu.addAction("⟳  Atualizar metadados", lambda: self._action_refresh_meta(row))
        menu.addSeparator()
        menu.addAction("🔍  Buscar legenda",      lambda: self._action_subtitle(row))
        menu.addAction("🌐  Traduzir legenda",    lambda: self._action_translate(row))
        menu.addSeparator()
        menu.addAction("📁  Abrir pasta",         lambda: self._action_folder(row))
        menu.addAction("✏  Editar episódio",      lambda: self._action_edit(row))
        menu.addSeparator()
        menu.addAction("🗑  Remover",             lambda: self._action_remove(row))
        menu.exec(self._table.viewport().mapToGlobal(pos))

    # ── Actions ──────────────────────────────────────────────────────────────

    def _action_play(self, row) -> None:
        import subprocess
        from app.core.config import get_final_dir
        final_dir = get_final_dir()
        pattern = row[_PATTERN].replace("/", "_").lower()
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
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QSpinBox, QFormLayout
        anime_id   = row[_ID]
        name       = row[_TITLE] or row[_PATTERN]
        current_ep = row[_LAST_EP] or 0

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

    def _action_refresh_meta(self, row) -> None:
        anime_id = row[_ID]
        pattern  = row[_PATTERN]
        name     = row[_TITLE] or pattern
        from app.core.downloader import refresh_single_metadata
        run_async(
            refresh_single_metadata(anime_id, pattern),
            on_done=lambda r: (
                self.refresh(),
                self._toast(f"Metadados atualizados — {name}", "success")
                if not isinstance(r, Exception) else
                self._toast(f"Erro: {r}", "error")
            ),
        )

    def _action_subtitle(self, row) -> None:
        anime_id = row[_ID]
        name     = row[_TITLE] or row[_PATTERN]
        from app.core.jobs.queue import job_queue
        run_async(
            job_queue.enqueue("subtitle", anime_id=anime_id),
            on_done=lambda r: self._toast(
                f"Busca de legenda enfileirada — {name}" if not isinstance(r, Exception)
                else f"Erro ao enfileirar: {r}",
                "info" if not isinstance(r, Exception) else "error",
            ),
        )

    def _action_translate(self, row) -> None:
        anime_id = row[_ID]
        name     = row[_TITLE] or row[_PATTERN]
        from app.core.jobs.queue import job_queue
        run_async(
            job_queue.enqueue("translation", anime_id=anime_id),
            on_done=lambda r: self._toast(
                f"Tradução enfileirada — {name}" if not isinstance(r, Exception)
                else f"Erro ao enfileirar: {r}",
                "info" if not isinstance(r, Exception) else "error",
            ),
        )

    def _action_folder(self, row) -> None:
        import subprocess
        from app.core.config import get_final_dir
        # Files are stored flat in final_dir (e.g. episodes/My Anime - S01E01.mkv),
        # never in per-anime subdirectories — so open final_dir directly.
        folder = get_final_dir()
        if os.path.isdir(folder):
            subprocess.Popen(["xdg-open", folder])
        else:
            self._toast("Pasta de episódios não encontrada", "error")

    def _action_edit(self, row) -> None:
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QSpinBox, QFormLayout
        anime_id   = row[_ID]
        name       = row[_TITLE] or row[_PATTERN]
        current_ep = row[_LAST_EP] or 0

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
        anime_id = row[_ID]
        name     = row[_TITLE] or row[_PATTERN]
        reply = QMessageBox.question(
            self, "Remover anime",
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
