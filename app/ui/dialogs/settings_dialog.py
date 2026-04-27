import os
import tkinter as tk
from tkinter import ttk, filedialog
from ...core.config import get_setting, get_final_dir, load_settings_sync
from ...core.database import set_setting
from ...utils.async_bridge import run_async

class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, log_callback):
        super().__init__(parent)
        self.parent = parent
        self.log_callback = log_callback
        self.title("Configurações")
        self.geometry("500x300")
        self.configure(bg="#2b2b2b")
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
        def browse_folder(var):
            path = filedialog.askdirectory()
            if path:
                var.set(path)

        # Download Path
        tk.Label(self, text="Pasta de Downloads (Monitorada):", bg="#2b2b2b", fg="#ffffff").pack(anchor=tk.W, padx=20, pady=(20, 0))
        dl_var = tk.StringVar(value=get_setting("download_path", os.path.join(os.path.expanduser("~"), "Downloads", "Torrents")))
        dl_frame = tk.Frame(self, bg="#2b2b2b")
        dl_frame.pack(fill=tk.X, padx=20, pady=5)
        tk.Entry(dl_frame, textvariable=dl_var, bg="#1e1e1e", fg="#ffffff", insertbackground="white").pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(dl_frame, text="Procurar...", command=lambda: browse_folder(dl_var)).pack(side=tk.LEFT, padx=(5, 0))

        # Organize Path
        tk.Label(self, text="Pasta Final (Organizada):", bg="#2b2b2b", fg="#ffffff").pack(anchor=tk.W, padx=20, pady=(20, 0))
        final_var = tk.StringVar(value=get_final_dir())
        final_frame = tk.Frame(self, bg="#2b2b2b")
        final_frame.pack(fill=tk.X, padx=20, pady=5)
        tk.Entry(final_frame, textvariable=final_var, bg="#1e1e1e", fg="#ffffff", insertbackground="white").pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(final_frame, text="Procurar...", command=lambda: browse_folder(final_var)).pack(side=tk.LEFT, padx=(5, 0))

        def save():
            async def do_save():
                await set_setting("download_path", dl_var.get())
                await set_setting("organize_path", final_var.get())
                load_settings_sync()
                if self.log_callback:
                    self.log_callback("Configurações salvas com sucesso!", "green")
                self.destroy()
            run_async(do_save())

        ttk.Button(self, text="Salvar", command=save).pack(pady=20)
