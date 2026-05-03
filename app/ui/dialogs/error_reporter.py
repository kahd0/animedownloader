import sys
import platform
import traceback
import tkinter as tk
from tkinter import ttk
import urllib.parse
import webbrowser

from ...core.config import VERSION, GITHUB_REPO


def show_error_dialog(parent, exc: BaseException, context: str = ""):
    if getattr(parent, "_error_dialog_open", False):
        return
    parent._error_dialog_open = True

    tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))

    win = tk.Toplevel(parent)
    win.title("Erro Inesperado")
    win.configure(bg="#1e1e1e")
    win.geometry("700x480")
    win.resizable(True, True)
    win.after_idle(lambda: win.grab_set() if win.winfo_exists() else None)

    def _on_close():
        parent._error_dialog_open = False
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", _on_close)

    tk.Label(
        win, text="Ocorreu um erro inesperado:", bg="#1e1e1e", fg="#ff6b6b",
        font=("Segoe UI", 12, "bold")
    ).pack(anchor="w", padx=16, pady=(16, 4))

    if context:
        tk.Label(
            win, text=context, bg="#1e1e1e", fg="#aaaaaa", font=("Segoe UI", 10)
        ).pack(anchor="w", padx=16, pady=(0, 8))

    frame = tk.Frame(win, bg="#1e1e1e")
    frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 8))

    text = tk.Text(
        frame, bg="#2a2a2a", fg="#f0f0f0", font=("Courier New", 9),
        relief=tk.FLAT, wrap=tk.WORD
    )
    sb = ttk.Scrollbar(frame, command=text.yview)
    text.configure(yscrollcommand=sb.set)
    sb.pack(side=tk.RIGHT, fill=tk.Y)
    text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    text.insert(tk.END, tb_str)
    text.configure(state=tk.DISABLED)

    btn_frame = tk.Frame(win, bg="#1e1e1e")
    btn_frame.pack(fill=tk.X, padx=16, pady=(0, 16))

    def _report():
        title = f"Bug: {type(exc).__name__}: {str(exc)[:80]}"
        body = (
            f"**Versão:** {VERSION}\n"
            f"**Python:** {sys.version.split()[0]}\n"
            f"**Sistema:** {platform.system()} {platform.release()}\n"
            f"\n## Traceback\n\n```\n{tb_str}```\n"
            f"\n## Passos para reproduzir\n\n"
            f"<!-- Descreva o que você estava fazendo quando o erro ocorreu -->\n"
        )
        url = (
            f"https://github.com/{GITHUB_REPO}/issues/new?"
            + urllib.parse.urlencode({"title": title, "body": body})
        )
        webbrowser.open(url)

    ttk.Button(btn_frame, text="Reportar no GitHub", command=_report).pack(side=tk.LEFT)
    ttk.Button(btn_frame, text="Fechar", command=_on_close).pack(side=tk.LEFT, padx=(8, 0))
