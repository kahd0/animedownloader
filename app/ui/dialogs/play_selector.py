import os
import re
import tkinter as tk
from tkinter import ttk
from ...core.downloader import open_path, get_final_dir

class PlaySelectorDialog(tk.Toplevel):
    def __init__(self, parent, anime_name, matches, log_callback):
        super().__init__(parent)
        self.parent = parent
        self.anime_name = anime_name
        self.matches = matches
        self.log_callback = log_callback

        self.title(f"Selecionar Episódio - {anime_name}")
        self.geometry("500x400")
        self.configure(bg="#1e1e1e")
        self.transient(parent)
        self.grab_set()

        self._center_dialog()
        self._build_ui()

    def _center_dialog(self):
        self.update_idletasks()
        x = self.parent.winfo_x() + (self.parent.winfo_width() // 2) - (self.winfo_width() // 2)
        y = self.parent.winfo_y() + (self.parent.winfo_height() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")

    def _build_ui(self):
        tk.Label(self, text="Vários episódios encontrados:", bg="#1e1e1e", 
                 fg="#ffffff", font=("Segoe UI", 10, "bold")).pack(pady=10)

        frame = tk.Frame(self, bg="#1e1e1e")
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.listbox = tk.Listbox(frame, bg="#2a2a2a", fg="#ffffff", font=("Segoe UI", 10), 
                             selectbackground="#1565c0", bd=0, highlightthickness=0)
        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=vsb.set)
        
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        # Inserir do mais novo para o mais antigo
        for m in reversed(self.matches):
            self.listbox.insert(tk.END, m)

        self.listbox.bind("<Double-Button-1>", lambda e: self._play_selected())
        ttk.Button(self, text="Reproduzir Selecionado", command=self._play_selected).pack(pady=10)
        ttk.Button(self, text="Cancelar", command=self.destroy).pack(pady=(0, 15))

    def _play_selected(self):
        sel = self.listbox.curselection()
        if sel:
            file_name = self.listbox.get(sel[0])
            path = os.path.join(get_final_dir(), file_name)
            if self.log_callback:
                self.log_callback(f"Abrindo: {file_name}", "green")
            open_path(path)
            self.destroy()
