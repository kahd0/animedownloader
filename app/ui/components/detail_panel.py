"""Anime detail panel — shown on card click (non-modal)."""
from __future__ import annotations

import os
import re

from PySide6.QtCore import Qt, QTimer, QPoint
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QDialog, QMessageBox, QInputDialog,
)

from app.ui.design import tokens as t
from app.utils.async_bridge import run_async


class DetailPanel(QDialog):
    def __init__(self, anime_data: tuple, parent=None):
        super().__init__(parent)
        _, title_p, last_ep, res, last_date, cover_url, official, airing, has_new, last_dl = anime_data
        self._anime_id  = anime_data[0]
        self._title_pat = title_p
        self._title     = official or title_p
        self._episode   = last_ep
        self._res       = res
        self._airing    = airing
        self._drag_pos: QPoint | None = None

        self.setWindowTitle(self._title)
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(860, 560)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet(f"background: {t.BG_DEEP};")

        self._build_ui()
        self._center_on_parent()
        QTimer.singleShot(10, self._load_cover)

    def _center_on_parent(self) -> None:
        parent = self.parent()
        if parent:
            pg = parent.geometry()
            x = pg.x() + (pg.width() - self.width()) // 2
            y = pg.y() + (pg.height() - self.height()) // 2
        else:
            from PySide6.QtWidgets import QApplication
            screen = QApplication.primaryScreen().geometry()
            x = (screen.width() - self.width()) // 2
            y = (screen.height() - self.height()) // 2
        self.move(x, y)

    # ── Drag to move ─────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    # ── UI ───────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Left: poster
        self._poster_lbl = QLabel()
        self._poster_lbl.setFixedWidth(240)
        self._poster_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._poster_lbl.setStyleSheet(f"background: {t.BG_SURFACE};")
        layout.addWidget(self._poster_lbl)

        # Right: info + actions
        right = QWidget()
        right.setStyleSheet("background: transparent;")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(t.SP8, t.SP5, t.SP8, t.SP8)
        rl.setSpacing(t.SP4)

        # Close button — white circle, turns red on hover
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(36, 36)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {t.BG_ELEVATED};
                color: {t.TEXT_PRIMARY};
                border: 1px solid {t.BG_BORDER};
                border-radius: 18px;
                font-size: 15px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {t.ERROR};
                border-color: {t.ERROR};
                color: white;
            }}
        """)
        close_btn.clicked.connect(self.close)
        close_row = QWidget()
        close_row.setStyleSheet("background: transparent;")
        cr = QHBoxLayout(close_row)
        cr.setContentsMargins(0, 0, 0, 0)
        cr.addStretch(1)
        cr.addWidget(close_btn)
        rl.addWidget(close_row)

        # Title
        title_lbl = QLabel(self._title)
        title_lbl.setStyleSheet(
            f"color: {t.TEXT_PRIMARY}; font-size: 24px; font-weight: 700; background: transparent;"
        )
        title_lbl.setWordWrap(True)
        rl.addWidget(title_lbl)

        # Meta
        airing_lower = (self._airing or "").lower()
        if "finished" in airing_lower or "complete" in airing_lower:
            status_text = "Finalizado"
        elif "currently" in airing_lower or airing_lower == "airing":
            status_text = "Em Exibição"
        elif "not yet" in airing_lower:
            status_text = "Em Breve"
        else:
            status_text = self._airing or "Desconhecido"

        ep_str = f"EP {self._episode:02d}" if self._episode else "EP —"
        meta = QLabel(f"{ep_str}  ·  {status_text}  ·  {self._res or '?'}")
        meta.setStyleSheet(f"color: {t.TEXT_SECONDARY}; font-size: 13px; background: transparent;")
        rl.addWidget(meta)

        # Primary actions
        btn_row = QWidget()
        btn_row.setStyleSheet("background: transparent;")
        brl = QHBoxLayout(btn_row)
        brl.setContentsMargins(0, 0, 0, 0)
        brl.setSpacing(t.SP3)

        play_btn = QPushButton("▶  ASSISTIR")
        play_btn.setFixedHeight(42)
        play_btn.setFixedWidth(160)
        play_btn.setStyleSheet(f"""
            QPushButton {{
                background: {t.ACCENT};
                color: white;
                border: none;
                border-radius: {t.RADIUS_MD}px;
                font-size: 14px;
                font-weight: 700;
            }}
            QPushButton:hover {{ background: {t.ACCENT_HOVER}; }}
        """)
        play_btn.clicked.connect(self._action_play)

        watched_btn = QPushButton("✓  JÁ VISTO")
        watched_btn.setFixedHeight(42)
        watched_btn.setFixedWidth(140)
        watched_btn.clicked.connect(self._action_watched)

        brl.addWidget(play_btn)
        brl.addWidget(watched_btn)
        brl.addStretch(1)
        rl.addWidget(btn_row)

        # Subtitle section
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setFixedHeight(1)
        sep1.setStyleSheet(f"background: {t.BG_BORDER}; border: none;")
        rl.addWidget(sep1)

        sub_label = QLabel("LEGENDA")
        sub_label.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: 11px; font-weight: 600;"
            f" letter-spacing: 1px; background: transparent;"
        )
        rl.addWidget(sub_label)

        sub_row = QWidget()
        sub_row.setStyleSheet("background: transparent;")
        srl = QHBoxLayout(sub_row)
        srl.setContentsMargins(0, 0, 0, 0)
        srl.setSpacing(t.SP2)

        sub_btn = QPushButton("🔍  Buscar Online")
        sub_btn.setFixedHeight(34)
        sub_btn.clicked.connect(self._action_subtitle)

        tl_btn = QPushButton("🌐  Traduzir PT-BR")
        tl_btn.setFixedHeight(34)
        tl_btn.clicked.connect(self._action_translate)

        srl.addWidget(sub_btn)
        srl.addWidget(tl_btn)
        srl.addStretch(1)
        rl.addWidget(sub_row)

        # Utility actions
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setFixedHeight(1)
        sep2.setStyleSheet(f"background: {t.BG_BORDER}; border: none;")
        rl.addWidget(sep2)

        util_row = QWidget()
        util_row.setStyleSheet("background: transparent;")
        url = QHBoxLayout(util_row)
        url.setContentsMargins(0, 0, 0, 0)
        url.setSpacing(t.SP2)

        for label, action in [
            ("📁  Pasta", self._action_folder),
            ("✏  Editar EP", self._action_edit),
            ("🗑  Remover", self._action_remove),
        ]:
            btn = QPushButton(label)
            btn.setFixedHeight(32)
            btn.clicked.connect(action)
            url.addWidget(btn)

        url.addStretch(1)
        rl.addWidget(util_row)
        rl.addStretch(1)

        layout.addWidget(right, 1)

    def _load_cover(self) -> None:
        from app.core.config import COVERS_DIR as COVER_DIR
        safe = re.sub(r'[^\w\s-]', '', self._title_pat).strip().lower().replace(' ', '_')
        for ext in (".jpg", ".png", ".jpeg", ".webp"):
            path = os.path.join(COVER_DIR, safe + ext)
            if os.path.exists(path):
                from app.ui.utils.image_cache import get_cover_pixmap
                px = get_cover_pixmap(path, 240, self.height())
                if px and not px.isNull():
                    self._poster_lbl.setPixmap(px.scaled(
                        240, self.height(),
                        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation,
                    ))
                return

    # ── Actions ──────────────────────────────────────────────────────────────

    def _find_video_files(self) -> list[str]:
        from app.core.config import get_final_dir
        from app.core.naming import matches_pattern
        final_dir = get_final_dir()
        if not os.path.exists(final_dir):
            return []
        exts = {".mkv", ".mp4", ".avi", ".mov", ".wmv"}
        return sorted(
            f for f in os.listdir(final_dir)
            if os.path.splitext(f)[1].lower() in exts and matches_pattern(f, self._title_pat)
        )

    def _action_play(self) -> None:
        files = self._find_video_files()
        if not files:
            QMessageBox.information(self, "Assistir", "Nenhum episódio encontrado na pasta de episódios.")
            return
        if len(files) == 1:
            from app.core.config import get_final_dir
            from app.core.downloader import open_path
            open_path(os.path.join(get_final_dir(), files[0]))
        else:
            from PySide6.QtWidgets import QListWidget, QDialogButtonBox
            dlg = QDialog(self)
            dlg.setWindowTitle("Selecionar Episódio")
            dlg.resize(460, 320)
            dlg.setStyleSheet(f"background: {t.BG_SURFACE}; color: {t.TEXT_PRIMARY};")
            vl = QVBoxLayout(dlg)
            lbl = QLabel("Selecione o episódio para assistir:")
            lbl.setStyleSheet(f"color: {t.TEXT_SECONDARY}; font-size: 13px;")
            vl.addWidget(lbl)
            lw = QListWidget()
            lw.setStyleSheet(f"""
                QListWidget {{
                    background: {t.BG_ELEVATED}; color: {t.TEXT_PRIMARY};
                    border: 1px solid {t.BG_BORDER}; border-radius: {t.RADIUS_MD}px;
                    font-size: 13px;
                }}
                QListWidget::item:selected {{ background: {t.ACCENT_MUTED}; color: {t.ACCENT}; }}
            """)
            for f in reversed(files):
                lw.addItem(f)
            lw.setCurrentRow(0)
            vl.addWidget(lw)
            btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            btns.accepted.connect(dlg.accept)
            btns.rejected.connect(dlg.reject)
            vl.addWidget(btns)
            lw.doubleClicked.connect(dlg.accept)
            if dlg.exec() == QDialog.DialogCode.Accepted and lw.currentItem():
                from app.core.config import get_final_dir
                from app.core.downloader import open_path
                open_path(os.path.join(get_final_dir(), lw.currentItem().text()))

    def _action_watched(self) -> None:
        from app.core.database import set_last_episode, clear_new_episode_flag
        run_async(set_last_episode(self._anime_id, self._episode))
        run_async(clear_new_episode_flag(self._anime_id))
        self.close()

    def _action_subtitle(self) -> None:
        QMessageBox.information(self, "Buscar Legenda", "Busca de legenda online ainda não disponível nesta versão.")

    def _action_translate(self) -> None:
        QMessageBox.information(self, "Traduzir", "Tradução automática ainda não disponível nesta versão.")

    def _action_folder(self) -> None:
        from app.core.config import get_final_dir
        from app.core.downloader import open_path
        folder = get_final_dir()
        os.makedirs(folder, exist_ok=True)
        open_path(folder)

    def _action_edit(self) -> None:
        new_ep, ok = QInputDialog.getInt(
            self, "Editar Episódio",
            f"Último episódio de {self._title}:",
            self._episode or 0,
            0, 99999,
        )
        if ok:
            from app.core.database import set_last_episode
            run_async(set_last_episode(self._anime_id, new_ep))
            self.close()

    def _action_remove(self) -> None:
        reply = QMessageBox.question(
            self, "Remover Anime",
            f"Remover «{self._title}» da lista de monitorados?\n\nOs arquivos locais NÃO serão apagados.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            from app.core.database import remove_anime
            run_async(remove_anime(self._anime_id))
            self.close()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(t.BG_DEEP))
