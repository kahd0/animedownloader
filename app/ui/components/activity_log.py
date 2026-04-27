import tkinter as tk
from tkinter import ttk
from datetime import datetime
from ..styles import get_log_tags_colors

class ActivityLog(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg="#1e1e1e", **kwargs)
        
        tk.Label(self, text="Log de Atividade", bg="#1e1e1e", fg="#888888",
                 font=("Segoe UI", 9)).pack(anchor=tk.W, padx=2)

        log_frame = tk.Frame(self, bg="#000000", relief=tk.SUNKEN, bd=1)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 2))
        log_frame.pack_propagate(False)

        self.log_text = tk.Text(
            log_frame, bg="#000000", fg="#ffffff", font=("Consolas", 9),
            state=tk.DISABLED, wrap=tk.WORD, bd=0, highlightthickness=0,
        )
        log_vsb = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_vsb.set)
        log_vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self._configure_tags()

    def _configure_tags(self):
        colors = get_log_tags_colors()
        for name, color in colors.items():
            self.log_text.tag_configure(name, foreground=color)
        self.log_text.tag_configure("white", foreground="white")

    def log(self, message: str, color: str = "white"):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{ts}] ", "white")
        self.log_text.insert(tk.END, message + "\n", color)
        self.log_text.configure(state=tk.DISABLED)
        self.log_text.see(tk.END)
