import sys
import platform
import tkinter as tk
from tkinter import ttk, filedialog
import urllib.parse
import webbrowser

from ...core.config import VERSION, GITHUB_REPO


class FeedbackDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self._image_path = None

        self.title("Relatar Problema")
        self.geometry("560x460")
        self.configure(bg="#121212")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self._center()
        self._build_ui()

    def _center(self):
        self.update_idletasks()
        x = self.parent.winfo_x() + (self.parent.winfo_width() // 2) - (self.winfo_width() // 2)
        y = self.parent.winfo_y() + (self.parent.winfo_height() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")

    def _build_ui(self):
        # Elementos fixos empilhados pelo fundo primeiro, para o text_frame
        # com expand=True ocupar apenas o espaço restante.

        # Botões (fundo)
        btn_frame = tk.Frame(self, bg="#121212")
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=16, pady=14)

        ttk.Button(btn_frame, text="Enviar no GitHub", command=self._submit).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Cancelar", command=self.destroy).pack(side=tk.LEFT, padx=(8, 0))
        tk.Label(btn_frame, text=f"v{VERSION.lstrip('v')}  •  {platform.system()}",
                 bg="#121212", fg="#555555", font=("Segoe UI", 8)).pack(side=tk.RIGHT)

        # Hint de anexo (acima dos botões)
        self._attach_hint = tk.Label(self, text="", bg="#121212", fg="#f0a500",
                                     font=("Segoe UI", 8), wraplength=526, justify="left")
        self._attach_hint.pack(side=tk.BOTTOM, anchor="w", padx=16)

        # Linha de anexo
        attach_frame = tk.Frame(self, bg="#121212")
        attach_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=16, pady=(10, 0))

        tk.Label(attach_frame, text="Anexo (opcional):", bg="#121212",
                 fg="#cccccc", font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT)
        self._attach_label = tk.Label(attach_frame, text="Nenhum arquivo selecionado",
                                      bg="#121212", fg="#888888", font=("Segoe UI", 9))
        self._attach_label.pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(attach_frame, text="Selecionar...", command=self._pick_file).pack(side=tk.RIGHT)

        # Topo: título
        tk.Label(self, text="Título", bg="#121212", fg="#cccccc",
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=16, pady=(12, 0))

        self._title_var = tk.StringVar()
        ttk.Entry(self, textvariable=self._title_var, font=("Segoe UI", 10)).pack(
            fill=tk.X, padx=16, pady=(4, 0))

        tk.Label(self, text="Descrição", bg="#121212", fg="#cccccc",
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=16, pady=(10, 0))

        # Área de texto — ocupa o espaço restante
        text_frame = tk.Frame(self, bg="#121212")
        text_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=(4, 0))

        self._desc = tk.Text(text_frame, bg="#1e1e1e", fg="#f0f0f0",
                             font=("Segoe UI", 10), relief=tk.FLAT,
                             wrap=tk.WORD, insertbackground="white")
        sb = ttk.Scrollbar(text_frame, command=self._desc.yview)
        self._desc.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._desc.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def _pick_file(self):
        path = filedialog.askopenfilename(
            title="Selecionar anexo",
            filetypes=[
                ("Imagens e Vídeos", "*.png *.jpg *.jpeg *.gif *.mp4 *.mkv *.webm"),
                ("Todos os arquivos", "*.*"),
            ]
        )
        if not path:
            return
        self._image_path = path
        name = path.split("/")[-1].split("\\")[-1]
        self._attach_label.configure(text=name, fg="#cccccc")
        self._attach_hint.configure(
            text="Após o GitHub abrir, arraste o arquivo para o campo de texto antes de enviar."
        )

    def _submit(self):
        title = self._title_var.get().strip()
        desc = self._desc.get("1.0", tk.END).strip()

        if not title:
            self._title_var.set("")
            self.focus()
            tk.messagebox.showwarning("Campo obrigatório", "Preencha o título do problema.", parent=self)
            return

        body = (
            f"**Versão:** {VERSION}\n"
            f"**Sistema:** {platform.system()} {platform.release()}\n"
            f"**Python:** {sys.version.split()[0]}\n"
            f"\n## Descrição\n\n{desc or '_(sem descrição)_'}\n"
        )
        if self._image_path:
            name = self._image_path.split("/")[-1].split("\\")[-1]
            body += f"\n## Anexo\n\n`{name}` — arraste o arquivo para este campo antes de enviar.\n"

        url = (
            f"https://github.com/{GITHUB_REPO}/issues/new?"
            + urllib.parse.urlencode({"title": title, "body": body})
        )
        webbrowser.open(url)
        self.destroy()
