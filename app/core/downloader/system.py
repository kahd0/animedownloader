"""Operações de sistema: abrir arquivos/pastas e disparar magnets."""
import os
import platform
import subprocess
import webbrowser


def open_path(path):
    """Abre um arquivo ou pasta com o aplicativo padrão do sistema."""
    try:
        if platform.system() == "Windows": os.startfile(path)
        elif platform.system() == "Darwin": subprocess.run(["open", path])
        else: subprocess.run(["xdg-open", path])
        return True
    except Exception as e:
        print(f"Erro ao abrir {path}: {e}")
        return False


def trigger_magnet(magnet_link):
    try:
        return open_path(magnet_link)
    except Exception as e:
        print(f"Erro ao abrir magnet: {e}")
        return webbrowser.open(magnet_link)
