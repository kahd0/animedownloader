"""Settings screen — inline categorized settings."""
from __future__ import annotations

import json

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QSpinBox, QCheckBox, QScrollArea,
    QFrame, QFileDialog, QSplitter, QListWidget, QListWidgetItem,
)

from app.ui.design import tokens as t
from app.utils.async_bridge import run_async
from app.providers.torrents.qbittorrent import QBittorrentProvider


CATEGORIES = [
    ("general",      "Geral"),
    ("downloads",    "Downloads"),
    ("qbittorrent",  "Torrent"),
    ("rss",          "RSS"),
    ("subtitles",    "Legendas"),
    ("translation",  "Tradução"),
    ("organization", "Organização"),
    ("appearance",   "Aparência"),
    ("about",        "Sobre"),
]


class _SettingsRow(QWidget):
    """Label + control pair."""

    def __init__(self, label: str, control: QWidget, description: str = "", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(t.SP4)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(2)

        lbl = QLabel(label)
        lbl.setStyleSheet(f"color: {t.TEXT_PRIMARY}; font-size: 13px; font-weight: 600; background: transparent;")
        ll.addWidget(lbl)

        if description:
            desc = QLabel(description)
            desc.setStyleSheet(f"color: {t.TEXT_MUTED}; font-size: 11px; background: transparent;")
            ll.addWidget(desc)

        layout.addWidget(left, 1)
        layout.addWidget(control)

    @staticmethod
    def path_input(value: str = "") -> tuple[QWidget, QLineEdit]:
        w = QWidget()
        wl = QHBoxLayout(w)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(t.SP2)
        inp = QLineEdit(value)
        inp.setFixedWidth(300)
        inp.setFixedHeight(34)
        btn = QPushButton("Pasta...")
        btn.setFixedHeight(34)
        btn.setFixedWidth(70)
        btn.clicked.connect(lambda: _browse_folder(inp))
        wl.addWidget(inp)
        wl.addWidget(btn)
        return w, inp

    @staticmethod
    def toggle(checked: bool = False) -> QCheckBox:
        cb = QCheckBox()
        cb.setChecked(checked)
        return cb

    @staticmethod
    def dropdown(options: list[str], current: str = "") -> QComboBox:
        cb = QComboBox()
        cb.addItems(options)
        if current in options:
            cb.setCurrentText(current)
        return cb

    @staticmethod
    def spinner(value: int = 0, min_: int = 0, max_: int = 9999) -> QSpinBox:
        sb = QSpinBox()
        sb.setMinimum(min_)
        sb.setMaximum(max_)
        sb.setValue(value)
        sb.setFixedWidth(80)
        sb.setFixedHeight(34)
        return sb


def _browse_folder(inp: QLineEdit) -> None:
    folder = QFileDialog.getExistingDirectory(inp, "Selecionar pasta", inp.text())
    if folder:
        inp.setText(folder)


class _SectionCard(QFrame):
    """Styled card wrapping a group of settings rows."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background: {t.BG_SURFACE};
                border: 1px solid {t.BG_BORDER};
                border-radius: {t.RADIUS_LG}px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(t.SP6, t.SP4, t.SP6, t.SP4)
        layout.setSpacing(t.SP4)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(f"color: {t.TEXT_MUTED}; font-size: 11px; font-weight: 600; letter-spacing: 1px; background: transparent;")
        layout.addWidget(title_lbl)

        self._rows_layout = layout

    def add_row(self, row: QWidget) -> None:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {t.BG_BORDER}; border: none;")
        self._rows_layout.addWidget(sep)
        self._rows_layout.addWidget(row)


class _RSSFeedRow(QWidget):
    """Single RSS feed row: enabled checkbox + name + url + delete button."""

    def __init__(self, name: str = "", url: str = "", enabled: bool = True, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(t.SP2)

        self._enabled = QCheckBox()
        self._enabled.setChecked(enabled)
        self._enabled.setFixedWidth(24)

        self._name = QLineEdit(name)
        self._name.setPlaceholderText("Nome")
        self._name.setFixedWidth(130)
        self._name.setFixedHeight(32)

        self._url = QLineEdit(url)
        self._url.setPlaceholderText("URL do feed RSS")
        self._url.setMinimumWidth(260)
        self._url.setFixedHeight(32)

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(32, 32)
        del_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {t.TEXT_MUTED};
                border: 1px solid {t.BG_BORDER};
                border-radius: {t.RADIUS_MD}px;
                font-size: 12px;
            }}
            QPushButton:hover {{ color: #e55; border-color: #e55; }}
        """)
        del_btn.clicked.connect(self._delete)

        layout.addWidget(self._enabled)
        layout.addWidget(self._name)
        layout.addWidget(self._url, 1)
        layout.addWidget(del_btn)

    def _delete(self) -> None:
        parent_widget = self.parent()
        if parent_widget is not None:
            layout = parent_widget.layout()
            if layout is not None:
                layout.removeWidget(self)
        self.setParent(None)
        self.deleteLater()

    def data(self) -> dict:
        return {
            "name": self._name.text().strip(),
            "url": self._url.text().strip(),
            "enabled": self._enabled.isChecked(),
        }


class _RSSSection(_SectionCard):
    """Manages a dynamic list of RSS feeds."""

    def __init__(self, feeds: list[dict], parent=None):
        super().__init__("FEEDS RSS", parent)

        self._list_container = QWidget()
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(2)
        self._rows_layout.addWidget(self._list_container)

        hint = QLabel("Suporta {show} na URL para feeds por anime (ex: nyaa.si/?c=0_0&f=0&q={show})")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {t.TEXT_MUTED}; font-size: 11px; background: transparent;")
        self._rows_layout.addWidget(hint)

        add_btn = QPushButton("+ Adicionar Feed")
        add_btn.setFixedHeight(32)
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {t.ACCENT};
                border: 1px solid {t.ACCENT};
                border-radius: {t.RADIUS_MD}px;
                font-size: 12px;
                padding: 0 {t.SP3}px;
            }}
            QPushButton:hover {{ background: {t.ACCENT_MUTED}; }}
        """)
        add_btn.clicked.connect(self._add_row)
        btn_row = QWidget()
        brl = QHBoxLayout(btn_row)
        brl.setContentsMargins(0, 0, 0, 0)
        brl.addStretch(1)
        brl.addWidget(add_btn)
        self._rows_layout.addWidget(btn_row)

        for feed in feeds:
            self._add_row(feed.get("name", ""), feed.get("url", ""), feed.get("enabled", True))

    def _add_row(self, name: str = "", url: str = "", enabled: bool = True) -> None:
        row = _RSSFeedRow(name, url, enabled, self._list_container)
        self._list_layout.addWidget(row)

    def get_feeds(self) -> list[dict]:
        feeds = []
        for i in range(self._list_layout.count()):
            item = self._list_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), _RSSFeedRow):
                d = item.widget().data()
                if d["url"]:
                    feeds.append(d)
        return feeds


class SettingsScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._controls: dict[str, QWidget] = {}
        self._config = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top bar
        topbar = QWidget()
        topbar.setFixedHeight(56)
        tbl = QHBoxLayout(topbar)
        tbl.setContentsMargins(t.CONTENT_PAD_H, 0, t.CONTENT_PAD_H, 0)

        title = QLabel("Configurações")
        title.setStyleSheet(f"color: {t.TEXT_PRIMARY}; font-size: 22px; font-weight: 700; background: transparent;")
        tbl.addWidget(title)
        tbl.addStretch(1)

        save_btn = QPushButton("Salvar Configurações")
        save_btn.setProperty("class", "primary")
        save_btn.setFixedHeight(36)
        save_btn.clicked.connect(self._save)
        tbl.addWidget(save_btn)
        root.addWidget(topbar)

        sep_top = QFrame()
        sep_top.setFrameShape(QFrame.Shape.HLine)
        sep_top.setFixedHeight(1)
        sep_top.setStyleSheet(f"background: {t.BG_BORDER}; border: none;")
        root.addWidget(sep_top)

        # Splitter: category list (left) + content (right)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)

        # Category list
        self._cat_list = QListWidget()
        self._cat_list.setFixedWidth(180)
        self._cat_list.setStyleSheet(f"""
            QListWidget {{
                background: {t.BG_SURFACE};
                border: none;
                outline: none;
            }}
            QListWidget::item {{
                color: {t.TEXT_SECONDARY};
                padding: {t.SP2}px {t.SP4}px;
                border-radius: {t.RADIUS_MD}px;
                margin: 1px 4px;
                font-size: 13px;
            }}
            QListWidget::item:selected {{
                background: {t.BG_ELEVATED};
                color: {t.TEXT_PRIMARY};
                font-weight: 600;
            }}
            QListWidget::item:hover {{
                background: {t.BG_ELEVATED};
                color: {t.TEXT_PRIMARY};
            }}
        """)
        for key, label in CATEGORIES:
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self._cat_list.addItem(item)
        self._cat_list.setCurrentRow(0)
        self._cat_list.currentItemChanged.connect(self._on_category_change)

        # Content scroll area
        self._content_scroll = QScrollArea()
        self._content_scroll.setWidgetResizable(True)
        self._content_scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._content_widget = QWidget()
        self._content_widget.setStyleSheet("background: transparent;")
        self._content_vlayout = QVBoxLayout(self._content_widget)
        self._content_vlayout.setContentsMargins(t.CONTENT_PAD_H, t.SP6, t.CONTENT_PAD_H, t.SP8)
        self._content_vlayout.setSpacing(t.SP4)
        self._content_vlayout.addStretch(1)
        self._content_scroll.setWidget(self._content_widget)

        splitter.addWidget(self._cat_list)
        splitter.addWidget(self._content_scroll)
        splitter.setSizes([180, 800])

        root.addWidget(splitter, 1)

        # Load config and build forms
        QTimer.singleShot(0, self._load_config)

    def _load_config(self) -> None:
        try:
            from app.core import config as cfg_mod
            class _Cfg:
                download_path = cfg_mod.get_source_dir()
                organize_path = cfg_mod.get_final_dir()
                subs_path     = cfg_mod.get_subs_dir()
                default_res   = cfg_mod.get_default_resolution()
                check_interval= int(cfg_mod.get_setting("check_interval", "10"))
                auto_organize = cfg_mod.is_auto_organize_enabled()
                download_ahead= cfg_mod.get_download_ahead()
                torrent_mode  = cfg_mod.get_torrent_mode()
                qbt_host      = cfg_mod.get_setting("qbt_host", "localhost")
                qbt_port      = cfg_mod.get_setting("qbt_port", "8080")
                qbt_user      = cfg_mod.get_setting("qbt_user", "")
                qbt_pass      = cfg_mod.get_setting("qbt_pass", "")
                opensubtitles_api_key = cfg_mod.get_setting("opensubtitles_api_key", "")
                gemini_api_key        = cfg_mod.get_gemini_api_key()
                rss_feeds_raw = cfg_mod.get_setting("rss_feeds", "[]") or "[]"
            self._config = _Cfg()
            self._build_all_sections()
            self._show_category("general")
        except Exception as e:
            print(f"Settings load error: {e}")

    def _build_all_sections(self) -> None:
        cfg = self._config

        self._sections: dict[str, list[_SectionCard]] = {}

        # General
        s1 = _SectionCard("PASTAS E DIRETÓRIOS")
        w, inp = _SettingsRow.path_input(getattr(cfg, "download_path", ""))
        self._controls["download_path"] = inp
        s1.add_row(_SettingsRow("Pasta de Downloads", w, "Onde os torrents são salvos"))
        w, inp = _SettingsRow.path_input(getattr(cfg, "organize_path", ""))
        self._controls["organize_path"] = inp
        s1.add_row(_SettingsRow("Destino Final", w, "Onde episódios organizados ficam"))
        w, inp = _SettingsRow.path_input(getattr(cfg, "subs_path", ""))
        self._controls["subs_path"] = inp
        s1.add_row(_SettingsRow("Legendas Temporárias", w, "Diretório temporário para legendas"))

        s2 = _SectionCard("SISTEMA")
        sp = _SettingsRow.spinner(getattr(cfg, "check_interval", 10), 1, 120)
        self._controls["check_interval"] = sp
        s2.add_row(_SettingsRow("Verificar a cada", sp, "Intervalo em minutos"))
        dd = _SettingsRow.dropdown(["1080p", "720p", "480p"], getattr(cfg, "default_res", "1080p"))
        self._controls["default_res"] = dd
        s2.add_row(_SettingsRow("Resolução Padrão", dd))
        cb = _SettingsRow.toggle(getattr(cfg, "auto_organize", True))
        self._controls["auto_organize"] = cb
        s2.add_row(_SettingsRow("Auto Organizar", cb, "Mover arquivos automaticamente após download"))

        self._sections["general"] = [s1, s2]

        # Torrent — modo de cliente
        s_mode = _SectionCard("CLIENTE DE TORRENT")
        mode_combo = QComboBox()
        for value, label in [
            ("auto",        "Automático (qBittorrent, senão app padrão)"),
            ("qbittorrent", "qBittorrent"),
            ("external",    "App de torrent padrão do sistema"),
        ]:
            mode_combo.addItem(label, value)
        idx = mode_combo.findData(getattr(cfg, "torrent_mode", "auto"))
        mode_combo.setCurrentIndex(idx if idx >= 0 else 0)
        mode_combo.setProperty("save_as_data", True)
        mode_combo.setFixedWidth(300)
        mode_combo.setFixedHeight(34)
        self._controls["torrent_mode"] = mode_combo
        s_mode.add_row(_SettingsRow(
            "Cliente de torrent", mode_combo,
            "App padrão funciona com qualquer cliente (Transmission, Deluge, etc.)",
        ))

        # qBittorrent (usado nos modos Automático e qBittorrent)
        s_qbt = _SectionCard("QBITTORRENT")
        for key, label, desc in [
            ("qbt_host", "Host", ""),
            ("qbt_port", "Porta", ""),
            ("qbt_user", "Usuário", ""),
            ("qbt_pass", "Senha", ""),
        ]:
            inp = QLineEdit(str(getattr(cfg, key, "")))
            inp.setFixedWidth(240)
            inp.setFixedHeight(34)
            if key == "qbt_pass":
                inp.setEchoMode(QLineEdit.EchoMode.Password)
            self._controls[key] = inp
            s_qbt.add_row(_SettingsRow(label, inp, desc))

        self._qbt_test_btn = QPushButton("Testar Conexão")
        self._qbt_test_btn.setProperty("class", "primary")
        self._qbt_test_btn.setFixedHeight(36)
        self._qbt_test_btn.clicked.connect(self._test_qbt_connection)
        btn_row = QWidget()
        btn_rl = QHBoxLayout(btn_row)
        btn_rl.setContentsMargins(0, 0, 0, 0)
        btn_rl.addStretch(1)
        btn_rl.addWidget(self._qbt_test_btn)
        s_qbt.add_row(btn_row)
        self._sections["qbittorrent"] = [s_mode, s_qbt]

        # Subtitles: OpenSubtitles key only
        s_subs = _SectionCard("CHAVES DE API")
        inp_os = QLineEdit(str(getattr(cfg, "opensubtitles_api_key", "")))
        inp_os.setFixedWidth(300)
        inp_os.setFixedHeight(34)
        inp_os.setEchoMode(QLineEdit.EchoMode.Password)
        self._controls["opensubtitles_api_key"] = inp_os
        s_subs.add_row(_SettingsRow("OpenSubtitles", inp_os, ""))
        self._sections["subtitles"] = [s_subs]

        # Translation: Gemini key only
        s_trans = _SectionCard("CHAVES DE API")
        inp_gem = QLineEdit(str(getattr(cfg, "gemini_api_key", "")))
        inp_gem.setFixedWidth(300)
        inp_gem.setFixedHeight(34)
        inp_gem.setEchoMode(QLineEdit.EchoMode.Password)
        self._controls["gemini_api_key"] = inp_gem
        s_trans.add_row(_SettingsRow("Google Gemini", inp_gem, "Para tradução contextual"))
        self._sections["translation"] = [s_trans]

        # Downloads section
        s_dl = _SectionCard("COMPORTAMENTO DO DOWNLOAD")
        sp_ahead = _SettingsRow.spinner(getattr(cfg, "download_ahead", 3), 1, 50)
        self._controls["download_ahead"] = sp_ahead
        s_dl.add_row(_SettingsRow(
            "Episódios adiantados",
            sp_ahead,
            "Quantos eps baixar além do último assistido",
        ))
        self._sections["downloads"] = [s_dl]

        # RSS section
        try:
            feeds = json.loads(getattr(cfg, "rss_feeds_raw", "[]"))
        except Exception:
            feeds = []
        self._rss_section = _RSSSection(feeds)
        self._sections["rss"] = [self._rss_section]

        # About / Atualizações
        from app.core.config import VERSION
        s_about = _SectionCard("SOBRE E ATUALIZAÇÕES")
        ver_lbl = QLabel(VERSION)
        ver_lbl.setStyleSheet(f"color: {t.TEXT_SECONDARY}; font-size: 13px; background: transparent;")
        s_about.add_row(_SettingsRow("Versão Atual", ver_lbl, "Versão instalada do aplicativo"))

        self._update_btn = QPushButton("Buscar Atualizações")
        self._update_btn.setProperty("class", "primary")
        self._update_btn.setFixedHeight(36)
        self._update_btn.clicked.connect(self._check_updates_manual)
        upd_row = QWidget()
        upd_rl = QHBoxLayout(upd_row)
        upd_rl.setContentsMargins(0, 0, 0, 0)
        upd_rl.addStretch(1)
        upd_rl.addWidget(self._update_btn)
        s_about.add_row(upd_row)
        self._sections["about"] = [s_about]

        # Placeholder sections
        for key in ["organization", "appearance"]:
            placeholder = _SectionCard(key.upper())
            placeholder.add_row(QLabel("Em breve..."))
            self._sections.setdefault(key, [placeholder])

    def _show_category(self, key: str) -> None:
        layout = self._content_vlayout
        # Clear (keep stretch)
        while layout.count() > 1:
            item = layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        for section in self._sections.get(key, []):
            layout.insertWidget(layout.count() - 1, section)

    def _on_category_change(self, current: QListWidgetItem, _) -> None:
        if current:
            key = current.data(Qt.ItemDataRole.UserRole)
            self._show_category(key)

    def _test_qbt_connection(self) -> None:
        host = self._controls["qbt_host"].text()
        port = self._controls["qbt_port"].text()
        user = self._controls["qbt_user"].text()
        password = self._controls["qbt_pass"].text()

        async def _do_test():
            provider = QBittorrentProvider(
                host=host,
                port=int(port) if port.isdigit() else 8080,
                username=user,
                password=password,
            )
            return await provider.is_available()

        def _on_result(result) -> None:
            from app.ui.components.toast import ToastManager
            if isinstance(result, Exception) or not result:
                ToastManager.instance().show("Falha na conexão com qBittorrent", "error")
            else:
                ToastManager.instance().show("qBittorrent conectado!", "success")

        run_async(_do_test(), on_done=_on_result)

    def _check_updates_manual(self) -> None:
        from app.ui.update_flow import check_for_updates

        def on_state(state: str) -> None:
            if state == "checking":
                self._update_btn.setEnabled(False)
                self._update_btn.setText("Verificando...")
            else:
                self._update_btn.setEnabled(True)
                self._update_btn.setText("Buscar Atualizações")

        check_for_updates(self, silent=False, on_state=on_state)

    def _save(self) -> None:
        if not self._config:
            return
        try:
            run_async(self._do_save(), on_done=self._on_saved)
        except Exception as e:
            print(f"Save error: {e}")

    async def _do_save(self):
        from app.core.database import set_setting
        from app.core import config as cfg_mod
        for key, control in self._controls.items():
            if isinstance(control, QLineEdit):
                await set_setting(key, control.text())
            elif isinstance(control, QSpinBox):
                await set_setting(key, str(control.value()))
            elif isinstance(control, QComboBox):
                if control.property("save_as_data"):
                    await set_setting(key, control.currentData())
                else:
                    await set_setting(key, control.currentText())
            elif isinstance(control, QCheckBox):
                await set_setting(key, str(control.isChecked()))
        if hasattr(self, "_rss_section"):
            feeds = self._rss_section.get_feeds()
            await set_setting("rss_feeds", json.dumps(feeds, ensure_ascii=False))
        cfg_mod.load_settings_sync()

    def _on_saved(self, result) -> None:
        try:
            from app.ui.components.toast import ToastManager
            if isinstance(result, Exception):
                ToastManager.instance().show("Erro ao salvar configurações", "error")
            else:
                ToastManager.instance().show("Configurações salvas", "success")
        except Exception:
            pass
