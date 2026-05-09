import asyncio
import os
import tkinter as tk
from tkinter import ttk
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
        self.configure(bg="#121212")
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
                 bg="#121212", fg="#ffffff", font=("Segoe UI", 10), wraplength=330).pack(pady=(16, 4))
        tk.Label(self, text="Vídeos e legendas serão removidos permanentemente.", 
                 bg="#121212", fg="#888888", font=("Segoe UI", 9)).pack()

        btn_frame = tk.Frame(self, bg="#121212")
        btn_frame.pack(pady=12)
        ttk.Button(btn_frame, text="Deletar", command=self._confirm).pack(side=tk.LEFT, padx=8)
        ttk.Button(btn_frame, text="Cancelar", command=self.destroy).pack(side=tk.LEFT, padx=8)

    def _confirm(self):
        files = list(self.files_to_delete)
        anime_id = self.anime_id
        log_cb = self.log_callback
        refresh_cb = self.refresh_callback

        async def do_all():
            deleted = 0
            for fpath in files:
                try:
                    await asyncio.to_thread(os.remove, fpath)
                    deleted += 1
                except Exception:
                    pass
            await clear_new_episode_flag(anime_id)
            return deleted

        def on_done(result):
            deleted = result if not isinstance(result, Exception) else 0
            if log_cb:
                log_cb(f"Limpeza concluída: {deleted} arquivo(s) removido(s).", "cyan")
            refresh_cb()

        run_async(do_all(), on_done=on_done)
        self.destroy()
