import tkinter as tk
from tkinter import ttk
from ...core.database import set_last_episode
from ...utils.async_bridge import run_async

class EpisodeEditorDialog(tk.Toplevel):
    def __init__(self, parent, anime_id, anime_name, current_ep, log_callback, on_success_callback):
        super().__init__(parent)
        self.parent = parent
        self.anime_id = anime_id
        self.anime_name = anime_name
        self.current_ep = current_ep
        self.log_callback = log_callback
        self.on_success_callback = on_success_callback

        self.title("Editar Episódio")
        self.configure(bg="#1e1e1e")
        self._center_dialog(340, 180)
        self.transient(parent)
        self.grab_set()

        self._build_ui()

    def _center_dialog(self, width, height):
        self.update_idletasks()
        x = self.parent.winfo_x() + (self.parent.winfo_width() // 2) - (width // 2)
        y = self.parent.winfo_y() + (self.parent.winfo_height() // 2) - (height // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _build_ui(self):
        tk.Label(self, text=self.anime_name, bg="#1e1e1e", fg="#ffffff", 
                 font=("Segoe UI", 10, "bold"), wraplength=310).pack(pady=(14, 4))
        
        tk.Label(self, text="Último episódio registrado:", bg="#1e1e1e", 
                 fg="#aaaaaa", font=("Segoe UI", 9)).pack()
        
        self.spinbox = ttk.Spinbox(self, from_=0, to=99999, width=10, font=("Segoe UI", 11))
        self.spinbox.set(self.current_ep)
        self.spinbox.pack(pady=6)

        btn_frame = tk.Frame(self, bg="#1e1e1e")
        btn_frame.pack(pady=10)
        
        ttk.Button(btn_frame, text="Salvar", command=self._save).pack(side=tk.LEFT, padx=8)
        ttk.Button(btn_frame, text="Cancelar", command=self.destroy).pack(side=tk.LEFT, padx=8)

    def _save(self):
        try:
            new_ep = int(self.spinbox.get())
        except ValueError:
            new_ep = self.current_ep

        def on_done(_):
            if self.log_callback:
                self.log_callback(f"Episódio de '{self.anime_name}' atualizado: {self.current_ep} → {new_ep}", "cyan")
            if self.on_success_callback:
                self.on_success_callback()
            self.destroy()

        run_async(set_last_episode(self.anime_id, new_ep), on_done=on_done)
