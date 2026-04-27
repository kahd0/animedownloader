import os
import tkinter as tk
from tkinter import ttk, filedialog
from ...core.config import (
    get_setting, get_final_dir, get_subs_dir, 
    get_default_resolution, is_auto_organize_enabled, 
    should_delete_on_watched, load_settings_sync
)
from ...core.database import set_setting
from ...utils.async_bridge import run_async

class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, log_callback):
        super().__init__(parent)
        self.parent = parent
        self.log_callback = log_callback
        self.title("Configurações")
        self.geometry("550x550")
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
        # Container com scroll se necessário
        main_frame = tk.Frame(self, bg="#2b2b2b")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        def browse_folder(var):
            path = filedialog.askdirectory()
            if path:
                var.set(path)

        # --- SEÇÃO DE PASTAS ---
        tk.Label(main_frame, text="Pastas", bg="#2b2b2b", fg="#4caf50", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, pady=(0, 10))

        # Download Path
        tk.Label(main_frame, text="Pasta de Downloads (Monitorada):", bg="#2b2b2b", fg="#ffffff").pack(anchor=tk.W)
        dl_var = tk.StringVar(value=get_setting("download_path", os.path.join(os.path.expanduser("~"), "Downloads", "Torrents")))
        dl_frame = tk.Frame(main_frame, bg="#2b2b2b")
        dl_frame.pack(fill=tk.X, pady=(5, 15))
        tk.Entry(dl_frame, textvariable=dl_var, bg="#1e1e1e", fg="#ffffff", insertbackground="white").pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(dl_frame, text="Procurar...", command=lambda: browse_folder(dl_var)).pack(side=tk.LEFT, padx=(5, 0))

        # Organize Path
        tk.Label(main_frame, text="Pasta Final (Organizada):", bg="#2b2b2b", fg="#ffffff").pack(anchor=tk.W)
        final_var = tk.StringVar(value=get_final_dir())
        final_frame = tk.Frame(main_frame, bg="#2b2b2b")
        final_frame.pack(fill=tk.X, pady=(5, 15))
        tk.Entry(final_frame, textvariable=final_var, bg="#1e1e1e", fg="#ffffff", insertbackground="white").pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(final_frame, text="Procurar...", command=lambda: browse_folder(final_var)).pack(side=tk.LEFT, padx=(5, 0))

        # Subs Path
        tk.Label(main_frame, text="Pasta de Legendas Temporárias:", bg="#2b2b2b", fg="#ffffff").pack(anchor=tk.W)
        subs_var = tk.StringVar(value=get_subs_dir())
        subs_frame = tk.Frame(main_frame, bg="#2b2b2b")
        subs_frame.pack(fill=tk.X, pady=(5, 15))
        tk.Entry(subs_frame, textvariable=subs_var, bg="#1e1e1e", fg="#ffffff", insertbackground="white").pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(subs_frame, text="Procurar...", command=lambda: browse_folder(subs_var)).pack(side=tk.LEFT, padx=(5, 0))

        ttk.Separator(main_frame, orient="horizontal").pack(fill=tk.X, pady=10)

        # --- SEÇÃO DE PREFERÊNCIAS ---
        tk.Label(main_frame, text="Preferências", bg="#2b2b2b", fg="#4caf50", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, pady=(0, 10))

        # Resolução Padrão
        res_frame = tk.Frame(main_frame, bg="#2b2b2b")
        res_frame.pack(fill=tk.X, pady=5)
        tk.Label(res_frame, text="Resolução Padrão:", bg="#2b2b2b", fg="#ffffff").pack(side=tk.LEFT)
        res_var = tk.StringVar(value=get_default_resolution())
        res_combo = ttk.Combobox(res_frame, textvariable=res_var, values=["1080p", "720p", "480p"], width=10, state="readonly")
        res_combo.pack(side=tk.LEFT, padx=10)

        # Intervalo de Verificação
        int_frame = tk.Frame(main_frame, bg="#2b2b2b")
        int_frame.pack(fill=tk.X, pady=5)
        tk.Label(int_frame, text="Intervalo de Verificação (minutos):", bg="#2b2b2b", fg="#ffffff").pack(side=tk.LEFT)
        interval_var = tk.StringVar(value=get_setting("check_interval", "10"))
        interval_spin = ttk.Spinbox(int_frame, from_=1, to=1440, textvariable=interval_var, width=10)
        interval_spin.pack(side=tk.LEFT, padx=10)

        # Auto-Organizar
        auto_org_var = tk.BooleanVar(value=is_auto_organize_enabled())
        tk.Checkbutton(main_frame, text="Organizar automaticamente após baixar", 
                       variable=auto_org_var, bg="#2b2b2b", fg="#ffffff", 
                       selectcolor="#1e1e1e", activebackground="#2b2b2b", 
                       activeforeground="#ffffff").pack(anchor=tk.W, pady=5)

        # Deletar ao marcar visto
        delete_watched_var = tk.BooleanVar(value=should_delete_on_watched())
        tk.Checkbutton(main_frame, text="Excluir arquivos ao marcar como assistido", 
                       variable=delete_watched_var, bg="#2b2b2b", fg="#ffffff", 
                       selectcolor="#1e1e1e", activebackground="#2b2b2b", 
                       activeforeground="#ffffff").pack(anchor=tk.W, pady=5)

        def save():
            async def do_save():
                await set_setting("download_path", dl_var.get())
                await set_setting("organize_path", final_var.get())
                await set_setting("subs_path", subs_var.get())
                await set_setting("default_res", res_var.get())
                await set_setting("check_interval", interval_var.get())
                await set_setting("auto_organize", str(auto_org_var.get()))
                await set_setting("delete_on_watched", str(delete_watched_var.get()))
                
                load_settings_sync()
                
                # Avisar a janela principal sobre a mudança do intervalo
                if hasattr(self.parent, 'update_check_timer'):
                    self.parent.update_check_timer()
                
                if self.log_callback:
                    self.log_callback("Configurações salvas com sucesso!", "green")
                self.destroy()
            run_async(do_save())

        ttk.Button(self, text="Salvar", command=save).pack(pady=20)
