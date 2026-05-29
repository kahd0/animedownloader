"""Anime detail panel — shown on card click (non-modal)."""
from __future__ import annotations

import os
import re
import weakref

from PySide6.QtCore import Qt, QTimer, QPoint
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QDialog, QMessageBox, QInputDialog, QScrollArea,
)

from app.ui.design import tokens as t
from app.utils.async_bridge import run_async

# (anime_id, ep_num) -> 'translating' | 'queued'
_active_translations: dict[tuple[int, int], str] = {}
_translation_queue: list[tuple[int, int, str]] = []  # (anime_id, ep_num, video_path)
_translation_running: bool = False
_open_panels: list = []  # weakrefs to open DetailPanel instances


def _get_live_panels() -> list:
    alive = [r for r in _open_panels if r() is not None]
    _open_panels[:] = alive
    return [r() for r in alive]


def _notify_panel_state(anime_id: int, ep_num: int, status: str) -> None:
    for panel in _get_live_panels():
        if panel._anime_id == anime_id:
            try:
                panel._update_tl_btn_state(ep_num, status)
            except RuntimeError:
                pass


def _process_translation_queue() -> None:
    global _translation_running
    if _translation_running or not _translation_queue:
        return
    anime_id, ep_num, video_path = _translation_queue.pop(0)
    _translation_running = True
    _active_translations[(anime_id, ep_num)] = 'translating'
    _notify_panel_state(anime_id, ep_num, 'translating')

    from app.core.downloader import translate_video_subtitle
    from app.utils.async_bridge import run_async as _run_async
    from app.ui.components.toast import ToastManager

    def _on_done(result):
        global _translation_running
        _translation_running = False
        ok = not isinstance(result, Exception) and result.get("ok", False)
        _active_translations.pop((anime_id, ep_num), None)
        _notify_panel_state(anime_id, ep_num, 'done' if ok else 'error')
        if isinstance(result, Exception):
            ToastManager.instance().show(f"Erro na tradução EP {ep_num:02d}: {result}", "error")
        elif not ok:
            ToastManager.instance().show(f"Falha EP {ep_num:02d}: {result.get('error')}", "error")
        else:
            ToastManager.instance().show(f"EP {ep_num:02d} traduzido com sucesso!", "success")
        _process_translation_queue()

    _run_async(translate_video_subtitle(video_path), on_done=_on_done)


class DetailPanel(QDialog):
    def __init__(self, anime_data: tuple, parent=None):
        super().__init__(parent)
        _, title_p, last_ep, res, last_date, cover_url, official, airing, has_new, last_dl, *rest = anime_data
        last_ready = rest[6] if len(rest) > 6 else (last_dl or 0)  # index 16 overall
        self._anime_id  = anime_data[0]
        self._title_pat = title_p
        self._title     = official or title_p
        self._episode   = last_ep
        self._res       = res
        self._airing    = airing
        self._drag_pos: QPoint | None = None
        self._last_ep   = last_ep or 0
        self._last_dl   = last_dl or 0
        self._last_ready = last_ready
        self._all_eps = self._all_eps_on_disk()  # list of (ep_num, filename)
        self._tl_btns: dict[int, QPushButton] = {}
        self._tl_timers: dict[int, QTimer] = {}
        self._tl_step: dict[int, int] = {}
        _open_panels.append(weakref.ref(self))

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

        current_ep = self._last_dl or self._episode
        if self._last_dl > self._last_ep and self._last_ep:
            ep_str = f"EP {self._last_ep:02d} → {self._last_dl:02d}"
        elif current_ep:
            ep_str = f"EP {current_ep:02d}"
        else:
            ep_str = "EP —"
        meta = QLabel(f"{ep_str}  ·  {status_text}  ·  {self._res or '?'}")
        meta.setStyleSheet(f"color: {t.TEXT_SECONDARY}; font-size: 13px; background: transparent;")
        rl.addWidget(meta)

        # Episodes section
        sep_eps = QFrame()
        sep_eps.setFrameShape(QFrame.Shape.HLine)
        sep_eps.setFixedHeight(1)
        sep_eps.setStyleSheet(f"background: {t.BG_BORDER}; border: none;")
        rl.addWidget(sep_eps)

        eps_label = QLabel("EPISÓDIOS")
        eps_label.setStyleSheet(
            f"color: {t.TEXT_MUTED}; font-size: 11px; font-weight: 600;"
            f" letter-spacing: 1px; background: transparent;"
        )
        rl.addWidget(eps_label)

        ep_scroll = QScrollArea()
        ep_scroll.setWidgetResizable(True)
        ep_scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll_h = max(min(len(self._all_eps) * 48 + 8, 240), 120)
        ep_scroll.setFixedHeight(scroll_h)
        ep_scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{
                background: {t.BG_ELEVATED}; width: 4px; border-radius: 2px;
            }}
            QScrollBar::handle:vertical {{
                background: {t.BG_BORDER}; border-radius: 2px;
            }}
        """)
        ep_container = QWidget()
        ep_container.setStyleSheet("background: transparent;")
        ep_vl = QVBoxLayout(ep_container)
        ep_vl.setContentsMargins(0, 4, 0, 4)
        ep_vl.setSpacing(4)

        if self._all_eps:
            for ep_num, filename in self._all_eps:  # already sorted newest-first
                row = self._make_episode_row(ep_num, filename)
                ep_vl.addWidget(row)
        else:
            empty_lbl = QLabel("Nenhum episódio na pasta")
            empty_lbl.setStyleSheet(
                f"color: {t.TEXT_MUTED}; font-size: 12px; background: transparent; border: none;"
            )
            ep_vl.addWidget(empty_lbl)

        ep_scroll.setWidget(ep_container)
        rl.addWidget(ep_scroll)

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

    # ── Episode row helpers ──────────────────────────────────────────────────

    def _make_episode_row(self, ep_num: int, filename: str) -> QWidget:
        row = QWidget()
        row.setFixedHeight(40)
        row.setStyleSheet(f"""
            QWidget {{
                background: {t.BG_SURFACE};
                border: 1px solid {t.BG_BORDER};
                border-radius: {t.RADIUS_MD}px;
            }}
        """)
        hl = QHBoxLayout(row)
        hl.setContentsMargins(12, 0, 8, 0)
        hl.setSpacing(8)

        ep_lbl = QLabel(f"EP {ep_num:02d}")
        ep_lbl.setFixedWidth(52)
        ep_lbl.setStyleSheet(
            f"color: {t.TEXT_PRIMARY}; font-size: 13px; font-weight: bold;"
            f" background: transparent; border: none;"
        )
        hl.addWidget(ep_lbl)

        if self._has_ptbr_subtitle(filename):
            badge = QLabel("PT-BR")
            badge.setStyleSheet(
                "background: #1a7a4a; color: white; font-size: 9px;"
                " padding: 2px 5px; border-radius: 3px; border: none;"
            )
            hl.addWidget(badge)

        hl.addStretch(1)

        play_btn = QPushButton("▶ Assistir")
        play_btn.setFixedHeight(28)
        play_btn.setFixedWidth(80)
        play_btn.setStyleSheet(f"""
            QPushButton {{
                background: {t.ACCENT};
                color: white;
                border: none;
                border-radius: {t.RADIUS_SM}px;
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background: {t.ACCENT_HOVER}; }}
        """)
        play_btn.clicked.connect(lambda _, e=ep_num: self._play_episode(e))
        hl.addWidget(play_btn)

        watched_btn = QPushButton("✓ Visto")
        watched_btn.setFixedHeight(28)
        watched_btn.setFixedWidth(80)
        watched_btn.setStyleSheet(f"""
            QPushButton {{
                background: {t.BG_ELEVATED};
                color: {t.TEXT_SECONDARY};
                border: 1px solid {t.BG_BORDER};
                border-radius: {t.RADIUS_SM}px;
                font-size: 11px;
            }}
            QPushButton:hover {{ color: {t.SUCCESS}; border-color: {t.SUCCESS}; }}
        """)
        watched_btn.clicked.connect(lambda _, e=ep_num: self._mark_watched_for(e))
        watched_btn.setVisible(ep_num > self._last_ep)
        hl.addWidget(watched_btn)

        sub_btn = QPushButton("🔍 Legenda")
        sub_btn.setFixedHeight(28)
        sub_btn.setFixedWidth(80)
        sub_btn.setStyleSheet(f"""
            QPushButton {{
                background: {t.BG_ELEVATED};
                color: {t.TEXT_SECONDARY};
                border: 1px solid {t.BG_BORDER};
                border-radius: {t.RADIUS_SM}px;
                font-size: 11px;
            }}
            QPushButton:hover {{ color: {t.TEXT_PRIMARY}; border-color: {t.INFO}; }}
        """)
        sub_btn.clicked.connect(lambda _, e=ep_num: self._search_subtitle_for(e))
        hl.addWidget(sub_btn)

        tl_btn = QPushButton("🌐 Traduzir")
        tl_btn.setFixedHeight(28)
        tl_btn.setFixedWidth(80)
        tl_btn.setStyleSheet(f"""
            QPushButton {{
                background: {t.BG_ELEVATED};
                color: {t.TEXT_SECONDARY};
                border: 1px solid {t.BG_BORDER};
                border-radius: {t.RADIUS_SM}px;
                font-size: 11px;
            }}
            QPushButton:hover {{ color: {t.TEXT_PRIMARY}; border-color: {t.TRANSLATING}; }}
        """)
        tl_btn.clicked.connect(lambda _, e=ep_num: self._translate_for(e))
        hl.addWidget(tl_btn)
        self._tl_btns[ep_num] = tl_btn

        state = _active_translations.get((self._anime_id, ep_num))
        if state:
            self._update_tl_btn_state(ep_num, state)

        return row

    def _play_episode(self, ep_num: int) -> None:
        """Play a specific episode by number."""
        files = self._find_video_files()
        pattern = re.compile(
            rf'[^0-9]{ep_num:02d}[^0-9]|[^0-9]{ep_num}[^0-9]'
            rf'|^{ep_num:02d}[^0-9]'
        )
        matched = [f for f in files if pattern.search(f)]
        if not matched:
            matched = [
                f for f in files
                if f' {ep_num:02d} ' in f or f'_{ep_num:02d}_' in f or f' {ep_num:02d}.' in f
            ]
        if not matched:
            matched = files
        if len(matched) == 1:
            from app.core.config import get_final_dir
            from app.core.downloader import open_path
            open_path(os.path.join(get_final_dir(), matched[0]))
        elif matched:
            from PySide6.QtWidgets import QListWidget, QDialogButtonBox
            dlg = QDialog(self)
            dlg.setWindowTitle(f"Episódio {ep_num:02d}")
            dlg.resize(460, 280)
            dlg.setStyleSheet(f"background: {t.BG_SURFACE}; color: {t.TEXT_PRIMARY};")
            vl = QVBoxLayout(dlg)
            lw = QListWidget()
            lw.setStyleSheet(f"""
                QListWidget {{
                    background: {t.BG_ELEVATED};
                    color: {t.TEXT_PRIMARY};
                    border: 1px solid {t.BG_BORDER};
                    border-radius: {t.RADIUS_MD}px;
                    font-size: 13px;
                }}
                QListWidget::item:selected {{ background: {t.ACCENT_MUTED}; color: {t.ACCENT}; }}
            """)
            for f in matched:
                lw.addItem(f)
            lw.setCurrentRow(0)
            vl.addWidget(lw)
            btns = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
            )
            btns.accepted.connect(dlg.accept)
            btns.rejected.connect(dlg.reject)
            vl.addWidget(btns)
            lw.doubleClicked.connect(dlg.accept)
            if dlg.exec() == QDialog.DialogCode.Accepted and lw.currentItem():
                from app.core.config import get_final_dir
                from app.core.downloader import open_path
                open_path(os.path.join(get_final_dir(), lw.currentItem().text()))
        else:
            QMessageBox.information(self, "Assistir", f"Nenhum arquivo encontrado para EP {ep_num:02d}.")

    def _search_subtitle_for(self, ep_num: int) -> None:
        QMessageBox.information(
            self, "Buscar Legenda",
            f"Busca de legenda para EP {ep_num:02d} ainda não disponível nesta versão."
        )

    def _translate_for(self, ep_num: int) -> None:
        files = self._find_video_files()
        pattern = re.compile(
            rf'[^0-9]{ep_num:02d}[^0-9]|[^0-9]{ep_num}[^0-9]'
            rf'|^{ep_num:02d}[^0-9]'
        )
        matched = [f for f in files if pattern.search(f)]
        if not matched:
            matched = [
                f for f in files
                if f' {ep_num:02d} ' in f or f'_{ep_num:02d}_' in f or f' {ep_num:02d}.' in f
            ]
        if not matched:
            matched = files

        if len(matched) == 1:
            self._start_translation(matched[0], ep_num)
        elif matched:
            from PySide6.QtWidgets import QListWidget, QDialogButtonBox
            dlg = QDialog(self)
            dlg.setWindowTitle(f"Traduzir Episódio {ep_num:02d}")
            dlg.resize(460, 280)
            dlg.setStyleSheet(f"background: {t.BG_SURFACE}; color: {t.TEXT_PRIMARY};")
            vl = QVBoxLayout(dlg)
            lw = QListWidget()
            lw.setStyleSheet(f"""
                QListWidget {{
                    background: {t.BG_ELEVATED};
                    color: {t.TEXT_PRIMARY};
                    border: 1px solid {t.BG_BORDER};
                    border-radius: {t.RADIUS_MD}px;
                    font-size: 13px;
                }}
                QListWidget::item:selected {{ background: {t.ACCENT_MUTED}; color: {t.ACCENT}; }}
            """)
            for f in matched:
                lw.addItem(f)
            lw.setCurrentRow(0)
            vl.addWidget(lw)
            btns = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
            )
            btns.accepted.connect(dlg.accept)
            btns.rejected.connect(dlg.reject)
            vl.addWidget(btns)
            lw.doubleClicked.connect(dlg.accept)
            if dlg.exec() == QDialog.DialogCode.Accepted and lw.currentItem():
                self._start_translation(lw.currentItem().text(), ep_num)
        else:
            QMessageBox.information(self, "Traduzir", f"Nenhum arquivo encontrado para EP {ep_num:02d}.")

    # ── Disk helpers ─────────────────────────────────────────────────────────

    def _all_eps_on_disk(self) -> list[tuple[int, str]]:
        """Return [(ep_num, filename)] for all matching video files, sorted newest-first."""
        try:
            from app.core.config import get_final_dir
            from app.core.naming import matches_pattern
            from app.utils.episode_parser import extract_episode_number
            final_dir = get_final_dir()
            if not os.path.isdir(final_dir):
                return []
            exts = {".mkv", ".mp4", ".avi", ".mov", ".wmv"}
            eps = []
            for f in os.listdir(final_dir):
                if os.path.splitext(f)[1].lower() not in exts:
                    continue
                if not matches_pattern(f, self._title_pat):
                    continue
                ep = extract_episode_number(f)
                if ep is not None:
                    eps.append((ep, f))
            return sorted(eps, reverse=True)
        except Exception:
            return []

    def _has_ptbr_subtitle(self, filename: str) -> bool:
        """Return True if a PT-BR subtitle file exists alongside the given video filename."""
        from app.core.config import get_final_dir
        final_dir = get_final_dir()
        base = os.path.splitext(os.path.join(final_dir, filename))[0]
        for ext in (".srt", ".ass", ".sub", ".ssa", ".vtt"):
            for candidate in (base + ".pt" + ext, base + ".pt-br" + ext, base + ".ptbr" + ext):
                if os.path.exists(candidate):
                    return True
        return False

    def _mark_watched_for(self, ep_num: int) -> None:
        from app.core.database import set_last_episode, clear_new_episode_flag

        # Find files for this specific episode
        all_files = self._find_video_files()
        pattern = re.compile(
            rf'[^0-9]{ep_num:02d}[^0-9]|[^0-9]{ep_num}[^0-9]|^{ep_num:02d}[^0-9]'
        )
        ep_files = [f for f in all_files if pattern.search(f)] or []

        delete_files = False
        if ep_files:
            msg = QMessageBox(self)
            msg.setWindowTitle("Marcar como Visto")
            msg.setText(f"Marcar <b>EP {ep_num:02d}</b> de {self._title} como visto?")
            msg.setInformativeText(
                f"{len(ep_files)} arquivo(s) encontrado(s) para este episódio.\n"
                "Deseja apagar os arquivos de vídeo e legendas do HD?"
            )
            msg.setIcon(QMessageBox.Icon.Question)
            keep_btn   = msg.addButton("Manter arquivos", QMessageBox.ButtonRole.NoRole)
            delete_btn = msg.addButton("Apagar do HD",    QMessageBox.ButtonRole.DestructiveRole)
            cancel_btn = msg.addButton("Cancelar",        QMessageBox.ButtonRole.RejectRole)
            msg.setDefaultButton(keep_btn)
            msg.exec()
            clicked = msg.clickedButton()
            if clicked is cancel_btn:
                return
            delete_files = (clicked is delete_btn)

        run_async(set_last_episode(self._anime_id, ep_num))
        run_async(clear_new_episode_flag(self._anime_id))

        if delete_files:
            self._delete_episode_files(ep_files)

        self.close()

    # ── Actions ──────────────────────────────────────────────────────────────

    def _eps_from_disk(self, last_watched: int) -> list[int]:
        """Return episode numbers present on disk that the user hasn't watched yet."""
        try:
            from app.core.config import get_final_dir
            from app.core.naming import matches_pattern
            from app.utils.episode_parser import extract_episode_number
            final_dir = get_final_dir()
            if not os.path.isdir(final_dir):
                return []
            exts = {".mkv", ".mp4", ".avi", ".mov", ".wmv"}
            eps: set[int] = set()
            for f in os.listdir(final_dir):
                if os.path.splitext(f)[1].lower() not in exts:
                    continue
                if not matches_pattern(f, self._title_pat):
                    continue
                ep = extract_episode_number(f)
                if ep is not None and ep > last_watched:
                    eps.add(ep)
            return sorted(eps)
        except Exception:
            return []

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

    def _delete_episode_files(self, video_files: list[str]) -> None:
        from app.core.config import get_final_dir
        final_dir = get_final_dir()
        sub_exts = {".ass", ".srt", ".sub", ".ssa", ".vtt"}
        deleted, errors = [], []
        for vf in video_files:
            vpath = os.path.join(final_dir, vf)
            base = os.path.splitext(vpath)[0]
            # Delete video
            try:
                os.remove(vpath)
                deleted.append(vf)
            except Exception as e:
                errors.append(f"{vf}: {e}")
            # Delete associated subtitle files (same base name, any sub ext)
            for ext in sub_exts:
                for candidate in (base + ext, base + ".pt" + ext):
                    if os.path.exists(candidate):
                        try:
                            os.remove(candidate)
                            deleted.append(os.path.basename(candidate))
                        except Exception:
                            pass
        if errors:
            QMessageBox.warning(
                self, "Apagar arquivos",
                "Alguns arquivos não puderam ser apagados:\n" + "\n".join(errors),
            )

    def _update_tl_btn_state(self, ep_num: int, status: str) -> None:
        if status == 'translating':
            self._set_tl_loading(ep_num, True)
        elif status == 'queued':
            btn = self._tl_btns.get(ep_num)
            if btn:
                # Stop any running animation first
                timer = self._tl_timers.pop(ep_num, None)
                if timer:
                    timer.stop()
                    timer.deleteLater()
                self._tl_step.pop(ep_num, None)
                btn.setEnabled(False)
                btn.setText("🕐 Na fila")
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {t.BG_ELEVATED};
                        color: {t.TEXT_MUTED};
                        border: 1px solid {t.BG_BORDER};
                        border-radius: {t.RADIUS_SM}px;
                        font-size: 11px;
                    }}
                """)
        elif status in ('done', 'error'):
            self._set_tl_loading(ep_num, False, success=(status == 'done'))

    def _set_tl_loading(self, ep_num: int, loading: bool, success: bool = True) -> None:
        btn = self._tl_btns.get(ep_num)
        if btn is None:
            return
        if loading:
            self._tl_step[ep_num] = 0
            btn.setEnabled(False)
            btn.setText("⏳ Traduzindo")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {t.BG_ELEVATED};
                    color: {t.TRANSLATING};
                    border: 1px solid {t.TRANSLATING};
                    border-radius: {t.RADIUS_SM}px;
                    font-size: 11px;
                }}
            """)
            timer = QTimer(self)
            timer.setInterval(500)
            def _tick(e=ep_num, b=btn):
                if e not in self._tl_step:
                    return
                self._tl_step[e] = (self._tl_step[e] + 1) % 4
                dots = "." * self._tl_step[e]
                b.setText(f"⏳ Traduzindo{dots}" if dots else "⏳ Traduzindo")
            timer.timeout.connect(_tick)
            timer.start()
            self._tl_timers[ep_num] = timer
        else:
            timer = self._tl_timers.pop(ep_num, None)
            if timer:
                timer.stop()
                timer.deleteLater()
            self._tl_step.pop(ep_num, None)
            btn.setEnabled(True)
            if success:
                btn.setText("✓ Traduzido")
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {t.BG_ELEVATED};
                        color: {t.SUCCESS};
                        border: 1px solid {t.SUCCESS};
                        border-radius: {t.RADIUS_SM}px;
                        font-size: 11px;
                    }}
                    QPushButton:hover {{ color: {t.TEXT_PRIMARY}; border-color: {t.TRANSLATING}; }}
                """)
            else:
                btn.setText("✗ Erro")
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {t.BG_ELEVATED};
                        color: {t.ERROR};
                        border: 1px solid {t.ERROR};
                        border-radius: {t.RADIUS_SM}px;
                        font-size: 11px;
                    }}
                    QPushButton:hover {{ color: {t.TEXT_PRIMARY}; border-color: {t.TRANSLATING}; }}
                """)

    def _start_translation(self, filename: str, ep_num: int = None) -> None:
        from app.core.config import get_final_dir
        from app.ui.components.toast import ToastManager
        video_path = os.path.join(get_final_dir(), filename)
        anime_id = self._anime_id

        if ep_num is None:
            # Fallback: no ep tracking, just run directly
            from app.core.downloader import translate_video_subtitle
            ToastManager.instance().show("Iniciando tradução...", "info")
            run_async(translate_video_subtitle(video_path))
            return

        key = (anime_id, ep_num)
        if key in _active_translations:
            return  # already running or queued

        if _translation_running or _translation_queue:
            _active_translations[key] = 'queued'
            _translation_queue.append((anime_id, ep_num, video_path))
            self._update_tl_btn_state(ep_num, 'queued')
            ToastManager.instance().show(f"EP {ep_num:02d} adicionado à fila de tradução.", "info")
        else:
            _active_translations[key] = 'translating'
            _translation_queue.append((anime_id, ep_num, video_path))
            _process_translation_queue()

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
