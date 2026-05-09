import os
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from ...core.config import (
    get_setting, get_final_dir, get_subs_dir,
    get_default_resolution, is_auto_organize_enabled,
    should_delete_on_watched, get_download_ahead, load_settings_sync,
    get_subtitle_sources,
    VERSION, GITHUB_REPO
)
from ...core.database import set_setting, get_monitored_animes, import_animes
from ...core.api import check_for_app_updates
from ...utils.async_bridge import run_async
from ...utils.updater import download_file, apply_update_and_restart

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
        # Frame para o botão Salvar (fixo no rodapé)
        footer_frame = tk.Frame(self, bg="#2b2b2b")
        footer_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=10)

        def save():
            async def do_save():
                await set_setting("download_path", dl_var.get())
                await set_setting("organize_path", final_var.get())
                await set_setting("subs_path", subs_var.get())
                await set_setting("default_res", res_var.get())
                await set_setting("check_interval", interval_var.get())
                await set_setting("auto_organize", str(auto_org_var.get()))
                await set_setting("delete_on_watched", str(delete_watched_var.get()))
                await set_setting("download_ahead", download_ahead_var.get())
                await set_setting("opensubtitles_api_key", os_key_var.get())
                await set_setting("rss_feeds", json.dumps(rss_feeds_list))

                for i, src in enumerate(sub_sources):
                    src["priority"] = i + 1
                    src["enabled"] = sub_enabled_vars[i].get()
                await set_setting("subtitle_sources", json.dumps(sub_sources))

                load_settings_sync()
                
                # Avisar a janela principal sobre a mudança do intervalo
                if hasattr(self.parent, 'update_check_timer'):
                    self.parent.update_check_timer()
                
                if self.log_callback:
                    self.log_callback("Configurações salvas com sucesso!", "green")
                self.destroy()
            run_async(do_save())

        ttk.Button(footer_frame, text="Salvar", command=save).pack()

        # Container principal com scroll
        container = tk.Frame(self, bg="#2b2b2b")
        container.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(container, bg="#2b2b2b", highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        
        main_frame = tk.Frame(canvas, bg="#2b2b2b")
        
        # Vincular scroll
        main_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        window_id = canvas.create_window((0, 0), window=main_frame, anchor="nw")
        
        # Ajustar largura do frame interno à largura do canvas
        def _on_canvas_configure(event):
            canvas.itemconfig(window_id, width=event.width)
        canvas.bind("<Configure>", _on_canvas_configure)
        
        canvas.configure(yscrollcommand=scrollbar.set)

        # Suporte a Scroll do Mouse
        def _on_mousewheel(event):
            if canvas.winfo_exists():
                if event.num == 4 or event.delta > 0:
                    canvas.yview_scroll(-1, "units")
                elif event.num == 5 or event.delta < 0:
                    canvas.yview_scroll(1, "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        canvas.bind_all("<Button-4>", _on_mousewheel)
        canvas.bind_all("<Button-5>", _on_mousewheel)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        def browse_folder(var):
            path = filedialog.askdirectory()
            if path:
                var.set(path)

        # --- SEÇÃO DE PASTAS ---
        tk.Label(main_frame, text="Pastas", bg="#2b2b2b", fg="#4caf50", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, padx=20, pady=(10, 10))

        # Download Path
        tk.Label(main_frame, text="Pasta de Downloads (Monitorada):", bg="#2b2b2b", fg="#ffffff").pack(anchor=tk.W, padx=20)
        dl_var = tk.StringVar(value=get_setting("download_path", os.path.join(os.path.expanduser("~"), "Downloads", "Torrents")))
        dl_frame = tk.Frame(main_frame, bg="#2b2b2b")
        dl_frame.pack(fill=tk.X, padx=20, pady=(5, 15))
        tk.Entry(dl_frame, textvariable=dl_var, bg="#1e1e1e", fg="#ffffff", insertbackground="white").pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(dl_frame, text="Procurar...", command=lambda: browse_folder(dl_var)).pack(side=tk.LEFT, padx=(5, 0))

        # Organize Path
        tk.Label(main_frame, text="Pasta Final (Organizada):", bg="#2b2b2b", fg="#ffffff").pack(anchor=tk.W, padx=20)
        final_var = tk.StringVar(value=get_final_dir())
        final_frame = tk.Frame(main_frame, bg="#2b2b2b")
        final_frame.pack(fill=tk.X, padx=20, pady=(5, 15))
        tk.Entry(final_frame, textvariable=final_var, bg="#1e1e1e", fg="#ffffff", insertbackground="white").pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(final_frame, text="Procurar...", command=lambda: browse_folder(final_var)).pack(side=tk.LEFT, padx=(5, 0))

        # Subs Path
        tk.Label(main_frame, text="Pasta de Legendas Temporárias:", bg="#2b2b2b", fg="#ffffff").pack(anchor=tk.W, padx=20)
        subs_var = tk.StringVar(value=get_subs_dir())
        subs_frame = tk.Frame(main_frame, bg="#2b2b2b")
        subs_frame.pack(fill=tk.X, padx=20, pady=(5, 15))
        tk.Entry(subs_frame, textvariable=subs_var, bg="#1e1e1e", fg="#ffffff", insertbackground="white").pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(subs_frame, text="Procurar...", command=lambda: browse_folder(subs_var)).pack(side=tk.LEFT, padx=(5, 0))

        ttk.Separator(main_frame, orient="horizontal").pack(fill=tk.X, padx=20, pady=10)

        # --- SEÇÃO DE PREFERÊNCIAS ---
        tk.Label(main_frame, text="Preferências", bg="#2b2b2b", fg="#4caf50", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, padx=20, pady=(0, 10))

        # Resolução Padrão
        res_frame = tk.Frame(main_frame, bg="#2b2b2b")
        res_frame.pack(fill=tk.X, padx=20, pady=5)
        tk.Label(res_frame, text="Resolução Padrão:", bg="#2b2b2b", fg="#ffffff").pack(side=tk.LEFT)
        res_var = tk.StringVar(value=get_default_resolution())
        res_combo = ttk.Combobox(res_frame, textvariable=res_var, values=["1080p", "720p", "480p"], width=10, state="readonly")
        res_combo.pack(side=tk.LEFT, padx=10)

        # Intervalo de Verificação
        int_frame = tk.Frame(main_frame, bg="#2b2b2b")
        int_frame.pack(fill=tk.X, padx=20, pady=5)
        tk.Label(int_frame, text="Intervalo de Verificação (minutos):", bg="#2b2b2b", fg="#ffffff").pack(side=tk.LEFT)
        interval_var = tk.StringVar(value=get_setting("check_interval", "10"))
        interval_spin = ttk.Spinbox(int_frame, from_=1, to=1440, textvariable=interval_var, width=10)
        interval_spin.pack(side=tk.LEFT, padx=10)

        # Auto-Organizar
        auto_org_var = tk.BooleanVar(value=is_auto_organize_enabled())
        tk.Checkbutton(main_frame, text="Organizar automaticamente após baixar", 
                       variable=auto_org_var, bg="#2b2b2b", fg="#ffffff", 
                       selectcolor="#1e1e1e", activebackground="#2b2b2b", 
                       activeforeground="#ffffff").pack(anchor=tk.W, padx=20, pady=5)

        # Deletar ao marcar visto
        delete_watched_var = tk.BooleanVar(value=should_delete_on_watched())
        tk.Checkbutton(main_frame, text="Excluir arquivos ao marcar como assistido",
                       variable=delete_watched_var, bg="#2b2b2b", fg="#ffffff",
                       selectcolor="#1e1e1e", activebackground="#2b2b2b",
                       activeforeground="#ffffff").pack(anchor=tk.W, padx=20, pady=5)

        # Buffer de download
        ahead_frame = tk.Frame(main_frame, bg="#2b2b2b")
        ahead_frame.pack(fill=tk.X, padx=20, pady=5)
        tk.Label(ahead_frame, text="Episódios no buffer de download:", bg="#2b2b2b", fg="#ffffff").pack(side=tk.LEFT)
        download_ahead_var = tk.StringVar(value=str(get_download_ahead()))
        ttk.Spinbox(ahead_frame, from_=0, to=20, textvariable=download_ahead_var, width=10).pack(side=tk.LEFT, padx=10)

        ttk.Separator(main_frame, orient="horizontal").pack(fill=tk.X, padx=20, pady=10)

        # --- SEÇÃO DE APIS EXTERNAS ---
        tk.Label(main_frame, text="APIs Externas", bg="#2b2b2b", fg="#4caf50", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, padx=20, pady=(0, 4))

        tk.Label(main_frame, text="OpenSubtitles API Key (fallback PT-BR):", bg="#2b2b2b", fg="#ffffff").pack(anchor=tk.W, padx=20)
        tk.Label(main_frame, text="Obtenha em opensubtitles.com/consumers → crie um app", bg="#2b2b2b", fg="#888888", font=("Segoe UI", 8)).pack(anchor=tk.W, padx=20)
        os_key_var = tk.StringVar(value=get_setting("opensubtitles_api_key", ""))
        tk.Entry(main_frame, textvariable=os_key_var, bg="#1e1e1e", fg="#ffffff", insertbackground="white", show="*").pack(fill=tk.X, padx=20, pady=(4, 15))

        ttk.Separator(main_frame, orient="horizontal").pack(fill=tk.X, padx=20, pady=10)

        # --- SEÇÃO FONTES DE EPISÓDIOS ---
        tk.Label(main_frame, text="Fontes de Episódios", bg="#2b2b2b", fg="#4caf50",
                 font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, padx=20, pady=(0, 4))
        tk.Label(main_frame, text='Feeds RSS extras além do SubsPlease. Use {show} na URL para busca por anime.',
                 bg="#2b2b2b", fg="#888888", font=("Segoe UI", 8), wraplength=480).pack(anchor=tk.W, padx=20)

        try:
            rss_feeds_list = json.loads(get_setting("rss_feeds", "[]"))
            if not isinstance(rss_feeds_list, list):
                rss_feeds_list = []
        except Exception:
            rss_feeds_list = []

        rss_frame = tk.Frame(main_frame, bg="#1e1e1e", relief=tk.SUNKEN, bd=1)
        rss_frame.pack(fill=tk.X, padx=20, pady=(6, 4))

        rss_listbox = tk.Listbox(rss_frame, bg="#1e1e1e", fg="#ffffff",
                                 selectbackground="#1565c0", height=4,
                                 font=("Segoe UI", 9), relief=tk.FLAT, bd=0)
        rss_listbox.pack(fill=tk.X, padx=4, pady=4)

        def _render_rss_list():
            rss_listbox.delete(0, tk.END)
            rss_listbox.insert(tk.END, "[✓] SubsPlease (padrão, sempre ativo)")
            rss_listbox.itemconfig(0, fg="#888888")
            for f in rss_feeds_list:
                state = "✓" if f.get("enabled", True) else "✗"
                rss_listbox.insert(tk.END, f"[{state}] {f['name']}  —  {f['url']}")
                rss_listbox.itemconfig(tk.END, fg="#4caf50" if f.get("enabled", True) else "#888888")

        _render_rss_list()

        rss_btn_frame = tk.Frame(main_frame, bg="#2b2b2b")
        rss_btn_frame.pack(anchor=tk.W, padx=20, pady=(0, 10))

        def _rss_add():
            dlg = tk.Toplevel(self)
            dlg.title("Adicionar Feed RSS")
            dlg.configure(bg="#2b2b2b")
            dlg.transient(self)
            dlg.grab_set()
            dlg.geometry("480x150")
            x = self.winfo_x() + self.winfo_width() // 2 - 240
            y = self.winfo_y() + self.winfo_height() // 2 - 75
            dlg.geometry(f"+{x}+{y}")
            tk.Label(dlg, text="Nome:", bg="#2b2b2b", fg="#ffffff").pack(anchor=tk.W, padx=20, pady=(10, 2))
            name_var2 = tk.StringVar()
            tk.Entry(dlg, textvariable=name_var2, bg="#1e1e1e", fg="#ffffff",
                     insertbackground="white").pack(fill=tk.X, padx=20)
            tk.Label(dlg, text="URL:", bg="#2b2b2b", fg="#ffffff").pack(anchor=tk.W, padx=20, pady=(8, 2))
            url_var2 = tk.StringVar()
            tk.Entry(dlg, textvariable=url_var2, bg="#1e1e1e", fg="#ffffff",
                     insertbackground="white").pack(fill=tk.X, padx=20)
            btn_f2 = tk.Frame(dlg, bg="#2b2b2b")
            btn_f2.pack(pady=10)
            def _confirm_add():
                n, u = name_var2.get().strip(), url_var2.get().strip()
                if n and u:
                    rss_feeds_list.append({"name": n, "url": u, "enabled": True})
                    _render_rss_list()
                dlg.destroy()
            ttk.Button(btn_f2, text="Adicionar", command=_confirm_add).pack(side=tk.LEFT, padx=8)
            ttk.Button(btn_f2, text="Cancelar", command=dlg.destroy).pack(side=tk.LEFT, padx=8)

        def _rss_remove():
            sel = rss_listbox.curselection()
            if not sel:
                return
            idx = sel[0] - 1  # -1 because SubsPlease is at index 0
            if idx < 0:
                return
            rss_feeds_list.pop(idx)
            _render_rss_list()

        def _rss_toggle():
            sel = rss_listbox.curselection()
            if not sel:
                return
            idx = sel[0] - 1
            if idx < 0:
                return
            rss_feeds_list[idx]["enabled"] = not rss_feeds_list[idx].get("enabled", True)
            _render_rss_list()
            rss_listbox.selection_set(sel[0])

        ttk.Button(rss_btn_frame, text="+ Adicionar", command=_rss_add).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(rss_btn_frame, text="Ativar/Desativar", command=_rss_toggle).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(rss_btn_frame, text="- Remover", command=_rss_remove).pack(side=tk.LEFT)

        ttk.Separator(main_frame, orient="horizontal").pack(fill=tk.X, padx=20, pady=10)

        # --- SEÇÃO FONTES DE LEGENDAS ---
        tk.Label(main_frame, text="Fontes de Legendas", bg="#2b2b2b", fg="#4caf50",
                 font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, padx=20, pady=(0, 4))
        tk.Label(main_frame, text="Ordem de prioridade para busca de legendas. Reordene com ↑↓.",
                 bg="#2b2b2b", fg="#888888", font=("Segoe UI", 8)).pack(anchor=tk.W, padx=20)

        try:
            sub_sources = get_subtitle_sources()
        except Exception:
            sub_sources = [
                {"id": "animetosho",    "name": "AnimeTosho",    "enabled": True, "priority": 1},
                {"id": "opensubtitles", "name": "OpenSubtitles", "enabled": True, "priority": 2},
            ]

        sub_enabled_vars = []
        sub_sources_frame = tk.Frame(main_frame, bg="#2b2b2b")
        sub_sources_frame.pack(fill=tk.X, padx=20, pady=(6, 10))

        def _build_sub_rows():
            for w in sub_sources_frame.winfo_children():
                w.destroy()
            sub_enabled_vars.clear()
            for i, src in enumerate(sub_sources):
                row = tk.Frame(sub_sources_frame, bg="#1e1e1e", pady=4)
                row.pack(fill=tk.X, pady=2)
                up_btn = ttk.Button(row, text="↑", width=2, command=lambda idx=i: _move_sub_source(idx, -1))
                up_btn.pack(side=tk.LEFT, padx=(4, 2))
                if i == 0:
                    up_btn.config(state="disabled")
                dn_btn = ttk.Button(row, text="↓", width=2, command=lambda idx=i: _move_sub_source(idx, 1))
                dn_btn.pack(side=tk.LEFT, padx=(0, 6))
                if i == len(sub_sources) - 1:
                    dn_btn.config(state="disabled")
                var = tk.BooleanVar(value=src.get("enabled", True))
                sub_enabled_vars.append(var)
                tk.Checkbutton(row, variable=var, text=src["name"],
                               bg="#1e1e1e", fg="#ffffff", selectcolor="#1e1e1e",
                               activebackground="#252525", activeforeground="#ffffff"
                               ).pack(side=tk.LEFT)
                tk.Label(row, text=f"  (prioridade {i + 1})", bg="#1e1e1e",
                         fg="#888888", font=("Segoe UI", 8)).pack(side=tk.LEFT)
                if src["id"] == "opensubtitles":
                    ttk.Button(row, text="⚙ API Key", command=_show_os_key_dialog).pack(side=tk.RIGHT, padx=8)

        def _move_sub_source(idx, direction):
            for i, var in enumerate(sub_enabled_vars):
                sub_sources[i]["enabled"] = var.get()
            new_idx = idx + direction
            if 0 <= new_idx < len(sub_sources):
                sub_sources[idx], sub_sources[new_idx] = sub_sources[new_idx], sub_sources[idx]
                _build_sub_rows()

        def _show_os_key_dialog():
            dlg = tk.Toplevel(self)
            dlg.title("OpenSubtitles API Key")
            dlg.configure(bg="#2b2b2b")
            dlg.transient(self)
            dlg.grab_set()
            dlg.geometry("480x120")
            x = self.winfo_x() + self.winfo_width() // 2 - 240
            y = self.winfo_y() + self.winfo_height() // 2 - 60
            dlg.geometry(f"+{x}+{y}")
            tk.Label(dlg, text="OpenSubtitles API Key:", bg="#2b2b2b", fg="#ffffff").pack(anchor=tk.W, padx=20, pady=(10, 2))
            tk.Label(dlg, text="Obtenha em opensubtitles.com/consumers → crie um app",
                     bg="#2b2b2b", fg="#888888", font=("Segoe UI", 8)).pack(anchor=tk.W, padx=20)
            os_key_dlg_var = tk.StringVar(value=os_key_var.get())
            tk.Entry(dlg, textvariable=os_key_dlg_var, bg="#1e1e1e", fg="#ffffff",
                     insertbackground="white", show="*").pack(fill=tk.X, padx=20, pady=(4, 0))
            btn_f3 = tk.Frame(dlg, bg="#2b2b2b")
            btn_f3.pack(pady=10)
            def _confirm_key():
                os_key_var.set(os_key_dlg_var.get())
                dlg.destroy()
            ttk.Button(btn_f3, text="Salvar", command=_confirm_key).pack(side=tk.LEFT, padx=8)
            ttk.Button(btn_f3, text="Cancelar", command=dlg.destroy).pack(side=tk.LEFT, padx=8)

        _build_sub_rows()

        ttk.Separator(main_frame, orient="horizontal").pack(fill=tk.X, padx=20, pady=10)

        # --- SEÇÃO DE BACKUP ---
        tk.Label(main_frame, text="Dados e Backup", bg="#2b2b2b", fg="#4caf50", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, padx=20, pady=(0, 10))
        
        backup_frame = tk.Frame(main_frame, bg="#2b2b2b")
        backup_frame.pack(fill=tk.X, padx=20, pady=5)
        
        ttk.Button(backup_frame, text="📤 Exportar Lista (JSON)", command=self._export_data).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(backup_frame, text="📥 Importar Lista (JSON)", command=self._import_data).pack(side=tk.LEFT)

        ttk.Separator(main_frame, orient="horizontal").pack(fill=tk.X, padx=20, pady=10)

        # --- SEÇÃO DE ATUALIZAÇÃO ---
        tk.Label(main_frame, text="Sobre e Atualizações", bg="#2b2b2b", fg="#4caf50", font=("Segoe UI", 10, "bold")).pack(anchor=tk.W, padx=20, pady=(0, 10))
        
        info_frame = tk.Frame(main_frame, bg="#2b2b2b")
        info_frame.pack(fill=tk.X, padx=20, pady=5)

        tk.Label(info_frame, text=f"Versão Atual: {VERSION}", bg="#2b2b2b", fg="#ffffff").pack(side=tk.LEFT)
        self._update_btn = ttk.Button(info_frame, text="🔍 Buscar Atualizações", command=self._check_updates)
        self._update_btn.pack(side=tk.LEFT, padx=20)

    def _export_data(self):
        async def do_export():
            animes = await get_monitored_animes()
            if not animes:
                self.log_callback("Nenhum anime para exportar.", "yellow")
                return
            
            # Converter lista de tuplas para lista de dicts
            data = []
            for a in animes:
                data.append({
                    "title_pattern": a[1],
                    "last_episode": a[2],
                    "resolution": a[3],
                    "cover_url": a[5],
                    "official_title": a[6],
                    "airing_status": a[7]
                })
            
            file_path = filedialog.asksaveasfilename(
                defaultextension=".json",
                filetypes=[("JSON files", "*.json")],
                initialfile="anime_list_backup.json"
            )
            
            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
                self.log_callback(f"Lista exportada com sucesso: {os.path.basename(file_path)}", "green")
        
        run_async(do_export())

    def _import_data(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json")]
        )
        
        if not file_path:
            return
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if not isinstance(data, list):
                raise ValueError("Formato de arquivo inválido.")

            if messagebox.askyesno("Confirmar Importação", f"Deseja importar {len(data)} animes?"):
                async def do_import():
                    await import_animes(data)
                    self.log_callback(f"{len(data)} animes importados com sucesso!", "green")
                    if hasattr(self.parent, '_refresh_table'):
                        self.parent._refresh_table()
                run_async(do_import())
                
        except Exception as e:
            messagebox.showerror("Erro na Importação", f"Não foi possível importar o arquivo:\n{e}")

    def _check_updates(self):
        import sys
        self._update_btn.config(state="disabled", text="Verificando...")

        def on_checked(update):
            self._update_btn.config(state="normal", text="🔍 Buscar Atualizações")
            if isinstance(update, Exception) or not update:
                messagebox.showinfo("Atualização", "Não foi possível verificar. Tente mais tarde.")
                return
            if update["tag_name"] == VERSION:
                messagebox.showinfo("Atualização", "Você já está na versão mais recente!")
                return

            body = (update.get("body") or "")[:300]
            is_frozen = getattr(sys, "frozen", False)
            has_asset = bool(update.get("asset_url")) and is_frozen

            if has_asset:
                choice = messagebox.askyesnocancel(
                    "Nova Versão Disponível",
                    f"Versão {update['tag_name']} disponível!\n\n"
                    f"{body}\n\n"
                    "Atualizar automaticamente? (o app será reiniciado)\n"
                    "'Não' abre o navegador."
                )
                if choice is True:
                    self._do_auto_update(update)
                elif choice is False:
                    import webbrowser
                    webbrowser.open(update["html_url"])
            else:
                if messagebox.askyesno(
                    "Nova Versão Disponível",
                    f"Versão {update['tag_name']} disponível!\n\nAbrir página de download?"
                ):
                    import webbrowser
                    webbrowser.open(update["html_url"])

        run_async(check_for_app_updates(GITHUB_REPO), on_done=on_checked)

    def _do_auto_update(self, update):
        import tempfile
        asset_url = update["asset_url"]
        file_name = update.get("file_name", "anime_monitor_update")
        tmp_path = os.path.join(tempfile.gettempdir(), file_name)

        self._update_btn.config(state="disabled", text="Baixando...")
        if self.log_callback:
            self.log_callback(f"Baixando v{update['tag_name']}...", "blue")

        def on_downloaded(ok):
            if isinstance(ok, Exception) or not ok:
                self._update_btn.config(state="normal", text="🔍 Buscar Atualizações")
                messagebox.showerror("Erro no Download", "Falha ao baixar a atualização. Tente manualmente.")
                return
            if self.log_callback:
                self.log_callback("Download concluído. Aplicando atualização...", "green")
            if messagebox.askyesno(
                "Pronto para Atualizar",
                "Download concluído! O app será fechado e reiniciado automaticamente.\n\nContinuar?"
            ):
                apply_update_and_restart(tmp_path)
            else:
                self._update_btn.config(state="normal", text="🔍 Buscar Atualizações")

        run_async(download_file(asset_url, tmp_path), on_done=on_downloaded)
