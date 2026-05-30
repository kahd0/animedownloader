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


def has_magnet_handler():
    """Detecta (best-effort) se há um cliente de torrent registrado para magnet:.

    Retorna True/False quando dá para determinar, ou None quando é desconhecido
    (nesse caso o chamador deve assumir sucesso para evitar falso alarme).
    """
    system = platform.system()
    try:
        if system == "Windows":
            import winreg
            try:
                with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"magnet\shell\open\command"):
                    return True
            except FileNotFoundError:
                return False
        if system == "Linux":
            result = subprocess.run(
                ["xdg-mime", "query", "default", "x-scheme-handler/magnet"],
                capture_output=True, text=True, timeout=5,
            )
            return bool(result.stdout.strip())
    except Exception:
        return None
    # macOS e demais: sem consulta confiável — desconhecido.
    return None


def trigger_magnet(magnet_link):
    """Envia o magnet ao cliente de torrent padrão do sistema.

    Retorna True se um cliente foi acionado, False se nenhum handler está
    registrado (nada acontecerá) — para o chamador poder avisar o usuário.
    """
    system = platform.system()
    try:
        if has_magnet_handler() is False:
            return False

        if system == "Windows":
            os.startfile(magnet_link)
            return True
        if system == "Darwin":
            result = subprocess.run(["open", magnet_link], timeout=10)
            return result.returncode == 0
        # Linux: Popen não bloqueia enquanto o cliente abre.
        subprocess.Popen(["xdg-open", magnet_link])
        return True
    except Exception as e:
        print(f"Erro ao abrir magnet: {e}")
        try:
            return bool(webbrowser.open(magnet_link))
        except Exception:
            return False
