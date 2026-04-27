import tkinter as tk
from tkinter import ttk
import os
from ...core.database import clear_new_episode_flag
from ...utils.async_bridge import run_async

class ConfirmClearDialog(tk.Toplevel):
    def __init__(self, parent, anime_id, pattern, files_to_delete, video_count, log_callback, refresh_callback):
        super().__init__(parent)
        self.parent = parent
        self.anime_id = anime_id
        self.pattern = pattern
        self.files_to_delete = files_to_delete
        self.video_count = video_count
        self.log_callback = log_callback
        self.refresh_callback = refresh_callback

        self.title("Confirmar Limpeza")
        self.configure(bg="#1e1e1e")
        self.transient(parent)
        self.grab_set()

        self._center_dialog(360, 150)
        self._build_ui()

    def _center_dialog(self, w, h):
        self.parent.update_idletasks()
        x = self.parent.winfo_x() + (self.parent.winfo_width() - w) // 2
        y = self.parent.winfo_y() + (self.parent.winfo_height() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self):
        tk.Label(self, text=f"Deletar {self.video_count} episódio(s) de '{self.pattern}'?", 
                 bg="#1e1e1e", fg="#ffffff", font=("Segoe UI", 10), wraplength=330).pack(pady=(16, 4))
        tk.Label(self, text="Vídeos e legendas serão removidos permanentemente.", 
                 bg="#1e1e1e", fg="#888888", font=("Segoe UI", 9)).pack()

        btn_frame = tk.Frame(self, bg="#1e1e1e")
        btn_frame.pack(pady=12)
        ttk.Button(btn_frame, text="Deletar", command=self._confirm).pack(side=tk.LEFT, padx=8)
        ttk.Button(btn_frame, text="Cancelar", command=self.destroy).pack(side=tk.LEFT, padx=8)

    def _confirm(self):
        deleted = 0
        for fpath in self.files_to_delete:
            try:
                os.remove(fpath)
                deleted += 1
                if self.log_callback:
                    self.log_callback(f"Deletado: {os.path.basename(fpath)}", "orange")
            except Exception as e:
                if self.log_callback:
                    self.log_callback(f"Erro ao deletar {os.path.basename(fpath)}: {e}", "red")
        
        if self.log_callback:
            self.log_callback(f"Limpeza concluída: {deleted} arquivo(s) removido(s).", "cyan")
            
        run_async(clear_new_episode_flag(self.anime_id), on_done=lambda _: self.refresh_callback())
        self.destroy()
