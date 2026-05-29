"""Verificação e aplicação de atualizações do aplicativo (camada UI Qt).

Reaproveita o backend agnóstico de UI:
- ``app.core.api.check_for_app_updates`` consulta o GitHub releases.
- ``app.utils.updater`` baixa o asset e aplica via script auxiliar + restart.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile

from PySide6.QtWidgets import QMessageBox

from app.core.api import check_for_app_updates
from app.core.config import VERSION, GITHUB_REPO
from app.utils.async_bridge import run_async
from app.utils.updater import download_file, apply_update_and_restart


def _parse_version(tag: str) -> tuple[int, ...]:
    """Extrai os números de uma tag (ex: 'v1.2.3' -> (1, 2, 3))."""
    nums = re.findall(r"\d+", tag or "")
    return tuple(int(n) for n in nums) or (0,)


def check_for_updates(parent=None, *, silent: bool = True, on_state=None) -> None:
    """Verifica no GitHub se há uma versão mais nova.

    silent=True  -> uso no startup; só interage se houver atualização.
    silent=False -> uso no botão manual; também avisa "já atualizado" / erro.
    on_state(state) -> callback opcional ("checking"/"idle") para feedback no botão.
    """
    if on_state:
        on_state("checking")

    def on_checked(update):
        if on_state:
            on_state("idle")

        if isinstance(update, Exception) or not update:
            if not silent:
                QMessageBox.information(
                    parent, "Atualização",
                    "Não foi possível verificar atualizações. Tente mais tarde.",
                )
            return

        remote = update.get("tag_name") or ""
        if _parse_version(remote) <= _parse_version(VERSION):
            if not silent:
                QMessageBox.information(
                    parent, "Atualização",
                    "Você já está na versão mais recente!",
                )
            return

        _prompt_update(parent, update)

    run_async(check_for_app_updates(GITHUB_REPO), on_done=on_checked)


def _prompt_update(parent, update) -> None:
    remote = update.get("tag_name")
    is_frozen = getattr(sys, "frozen", False)
    has_asset = bool(update.get("asset_url")) and is_frozen
    notes = (update.get("body") or "").strip()
    notes_preview = f"\n\n{notes[:300]}" if notes else ""

    if has_asset:
        reply = QMessageBox.question(
            parent, "Nova Versão Disponível",
            f"Versão {remote} disponível!{notes_preview}\n\n"
            "Atualizar automaticamente? (o app será reiniciado)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            _apply_auto_update(parent, update)
        return

    # Sem asset compatível ou rodando do código-fonte -> abrir página de release.
    reply = QMessageBox.question(
        parent, "Nova Versão Disponível",
        f"Versão {remote} disponível!{notes_preview}\n\nAbrir página de download?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
    )
    if reply == QMessageBox.StandardButton.Yes:
        import webbrowser
        webbrowser.open(
            update.get("html_url") or f"https://github.com/{GITHUB_REPO}/releases"
        )


def _apply_auto_update(parent, update) -> None:
    file_name = update.get("file_name") or "anime_monitor_update"
    tmp_path = os.path.join(tempfile.gettempdir(), file_name)

    try:
        from app.ui.components.toast import ToastManager
        ToastManager.instance().show(
            f"Baixando atualização {update.get('tag_name')}...", "info"
        )
    except Exception:
        pass

    def on_downloaded(ok):
        if isinstance(ok, Exception) or not ok:
            QMessageBox.critical(
                parent, "Erro no Download",
                "Falha ao baixar a atualização. Tente novamente mais tarde.",
            )
            return
        QMessageBox.information(
            parent, "Pronto para Atualizar",
            "Download concluído. O aplicativo será reiniciado para aplicar a atualização.",
        )
        apply_update_and_restart(tmp_path)

    run_async(download_file(update["asset_url"], tmp_path), on_done=on_downloaded)
