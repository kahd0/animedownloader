import os
import re
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime

from ..core.config import (
    STATUS_PT, get_final_dir, VERSION, GITHUB_REPO
)
from ..core.database import (
    init_db, get_monitored_animes, remove_anime,
    update_anime_metadata, clear_new_episode_flag,
    get_setting as get_setting_sync
)
from ..core.downloader import (
    check_for_updates, organize_downloads, open_path,
    refresh_single_metadata, refresh_all_metadata,
    get_subtitle_candidates_for_anime, matches_pattern,
    download_chosen_subtitle
)
from ..core.api import check_for_app_updates
from ..utils.async_bridge import run_async, set_app_ref, stop_loop

# Importação de Componentes e Diálogos
from .styles import apply_styles
from .components.activity_log import ActivityLog
from .components.sidebar import AnimeSidebar
from .dialogs.settings_dialog import SettingsDialog
from .dialogs.episode_editor import EpisodeEditorDialog
from .dialogs.subtitle_selector import SubtitleQueueProcessor
from .dialogs.anime_adder import AnimeAdderLogic
from .dialogs.play_selector import PlaySelectorDialog
from .dialogs.confirm_clear import ConfirmClearDialog

class AnimeMonitorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        set_app_ref(self)

        self.title("Anime Monitor")
        self.geometry("1060x700")
        self.configure(bg="#1e1e1e")
        self.resizable(True, True)

        self._anime_data: dict = {}
        self._suggest_after_id = None
        self._suggest_popup = None

        self._build_ui()
        self._apply_custom_styles()
        
        self.adder_logic = AnimeAdderLogic(self, self.log, self._refresh_table)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        run_async(init_db(), on_done=lambda _: run_async(
            self._load_table_async(), on_done=self._on_table_loaded
        ))
        self.after(600_000, self._periodic_refresh)
        self.after(500, self._action_refresh)
        self.after(2000, self._check_app_updates)

    def _apply_custom_styles(self):
        apply_styles(self)
        self.tree.tag_configure("airing",   foreground="#4caf50")
        self.tree.tag_configure("finished", foreground="#888888")
        self.tree.tag_configure("upcoming", foreground="#2196f3")
        self.tree.tag_configure("new_ep",   background="#1b3328")

    def _build_ui(self):
        # Frame Principal Superior (Tabela + Sidebar)
        top_container = tk.Frame(self, bg="#1e1e1e")
        top_container.pack(fill=tk.BOTH, expand=True, padx=8, pady=(8, 4))

        # Tabela
        table_frame = tk.Frame(top_container, bg="#1e1e1e")
        table_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        cols = ("ID", "Anime", "Último Ep", "Resolução", "Último Download", "Status")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="browse")
        for col in cols:
            self.tree.heading(col, text=col)
        self.tree.column("ID",             width=40,  anchor=tk.CENTER)
        self.tree.column("Anime",          width=280)
        self.tree.column("Último Ep",      width=75,  anchor=tk.CENTER)
        self.tree.column("Resolução",      width=75,  anchor=tk.CENTER)
        self.tree.column("Último Download",width=120, anchor=tk.CENTER)
        self.tree.column("Status",         width=110, anchor=tk.CENTER)

        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<<TreeviewSelect>>", self._on_row_select)
        self.tree.bind("<Button-3>", self._show_context_menu)
        self.tree.bind("<Double-Button-1>", lambda e: self._action_edit_episode())

        # Sidebar Component
        self.sidebar = AnimeSidebar(top_container)
        self.sidebar.pack(side=tk.RIGHT, fill=tk.Y, padx=(6, 0))

        # Input Area
        input_frame = tk.Frame(self, bg="#1e1e1e")
        input_frame.pack(fill=tk.X, padx=8, pady=4)

        self.entry = ttk.Entry(input_frame, font=("Segoe UI", 11))
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        self.entry.bind("<Return>", lambda e: self._add_anime())
        self.entry.bind("<KeyRelease>", self._on_entry_key)
        self.entry.bind("<FocusOut>", lambda e: self.after(150, self._close_suggestions))

        ttk.Button(input_frame, text="Adicionar", command=self._add_anime).pack(side=tk.LEFT, padx=(8, 0))

        # Action Buttons
        action_frame = tk.Frame(self, bg="#1e1e1e")
        action_frame.pack(fill=tk.X, padx=8, pady=4)

        ttk.Button(action_frame, text="Verificar Agora",    command=self._action_refresh).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(action_frame, text="Organizar",          command=self._action_organize).pack(side=tk.LEFT, padx=4)
        ttk.Button(action_frame, text="Buscar Legendas",    command=self._action_download_subs).pack(side=tk.LEFT, padx=4)
        ttk.Button(action_frame, text="Remover Selecionado",command=self._action_delete).pack(side=tk.LEFT, padx=4)
        ttk.Button(action_frame, text="▶ Play",             command=self._action_play).pack(side=tk.LEFT, padx=4)
        ttk.Button(action_frame, text="📁 Abrir Pasta",     command=self._action_open_folder).pack(side=tk.LEFT, padx=4)
        ttk.Button(action_frame, text="⚙ Configurações",    command=self._action_open_settings).pack(side=tk.LEFT, padx=4)

        # Log Component
        self.activity_log = ActivityLog(self, height=180)
        self.activity_log.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(0, 8))

    def log(self, message: str, color: str = "white"):
        self.activity_log.log(message, color)

    def _check_app_updates(self):
        async def check():
            update = await check_for_app_updates(GITHUB_REPO)
            if update and update["tag_name"] != VERSION:
                if messagebox.askyesno("Nova Versão disponível", f"Uma nova versão ({update['tag_name']}) disponível!\n\nDescarregar?"):
                    import webbrowser
                    webbrowser.open(update["html_url"])
        run_async(check())

    async def _load_table_async(self):
        return await get_monitored_animes()

    def _on_table_loaded(self, animes):
        if isinstance(animes, Exception):
            self.log(f"Erro ao carregar tabela: {animes}", "red")
            return
        for row in self.tree.get_children():
            self.tree.delete(row)
        self._anime_data.clear()

        for anime in animes:
            iid = str(anime[0])
            self._anime_data[iid] = anime
            display_title = anime[6] or anime[1]
            status_raw = anime[7] or ""
            status_pt = STATUS_PT.get(status_raw, status_raw or "—")
            has_new = bool(anime[8])

            tags = []
            if status_raw == "Currently Airing": tags.append("airing")
            elif status_raw == "Finished Airing": tags.append("finished")
            elif status_raw == "Not yet aired": tags.append("upcoming")
            if has_new: tags.append("new_ep")

            self.tree.insert("", tk.END, iid=iid, tags=tags, values=[
                str(anime[0]), ("🔥 " if has_new else "") + display_title,
                str(anime[2]), str(anime[3]), anime[4] or "—", status_pt,
            ])

    def _refresh_table(self):
        run_async(self._load_table_async(), on_done=self._on_table_loaded)

    def _on_row_select(self, event=None):
        selected = self.tree.selection()
        if not selected: return
        iid = selected[0]
        data = self._anime_data.get(iid)
        if data:
            self.sidebar.update_info(iid, data)

    def _on_entry_key(self, event):
        if event.keysym in ("Down", "Up"):
            if self._suggest_popup: self._suggest_popup.focus_set()
            return
        if event.keysym == "Escape":
            self._close_suggestions()
            return
        if self._suggest_after_id: self.after_cancel(self._suggest_after_id)
        query = self.entry.get().strip()
        if len(query) < 3:
            self._close_suggestions()
            return
        self._suggest_after_id = self.after(420, lambda: self._fetch_suggestions(query))

    def _fetch_suggestions(self, query):
        from ..core.downloader import search_subsplease_shows
        def on_done(results):
            if results and not isinstance(results, Exception):
                self._show_suggestions(results)
        run_async(search_subsplease_shows(query), on_done=on_done)

    def _show_suggestions(self, titles):
        self._close_suggestions()
        ex = self.entry.winfo_rootx()
        ey = self.entry.winfo_rooty() + self.entry.winfo_height()
        popup = tk.Toplevel(self)
        popup.wm_overrideredirect(True)
        popup.geometry(f"{self.entry.winfo_width()}x{min(len(titles), 8) * 24}+{ex}+{ey}")
        self._suggest_popup = popup
        lb = tk.Listbox(popup, bg="#2a2a2a", fg="#ffffff", font=("Segoe UI", 10), bd=0)
        lb.pack(fill=tk.BOTH, expand=True)
        for t in titles: lb.insert(tk.END, t)
        def select(event=None):
            sel = lb.curselection()
            if sel:
                self.entry.delete(0, tk.END)
                self.entry.insert(0, lb.get(sel[0]))
            self._close_suggestions()
        lb.bind("<ButtonRelease-1>", select)
        lb.bind("<Return>", select)

    def _close_suggestions(self):
        if self._suggest_popup:
            self._suggest_popup.destroy()
            self._suggest_popup = None

    def _action_refresh(self):
        self.log("Verificando novas releases...", "blue")
        def on_done(result):
            if result and not isinstance(result, Exception):
                for item in result: self.log(f"DOWNLOAD INICIADO: {item}", "green")
                self._refresh_table()
            self._action_organize()
        run_async(check_for_updates(), on_done=on_done)

    def _action_organize(self):
        self.log("Organizando arquivos finalizados...", "blue")
        def on_done(result):
            if result and not isinstance(result, Exception):
                for f in result: self.log(f"ORGANIZADO: {f}", "cyan")
        run_async(organize_downloads(), on_done=on_done)

    def _action_play(self):
        selected = self.tree.selection()
        if not selected: return
        data = self._anime_data.get(selected[0])
        if not data: return
        pattern = data[1].lower()
        final_dir = get_final_dir()
        if not os.path.exists(final_dir): return
        matches = [f for f in os.listdir(final_dir) if f.lower().endswith((".mkv", ".mp4")) and matches_pattern(f, pattern)]
        if not matches:
            self.log(f"Nenhum episódio encontrado para '{pattern}'.", "yellow")
            return
        if len(matches) == 1:
            open_path(os.path.join(final_dir, matches[0]))
        else:
            PlaySelectorDialog(self, data[6] or data[1], matches, self.log)

    def _action_mark_watched(self):
        selected = self.tree.selection()
        if not selected: return
        iid = selected[0]
        data = self._anime_data.get(iid)
        if not data: return
        pattern = data[1]
        final_dir = get_final_dir()
        matches = [f for f in os.listdir(final_dir) if matches_pattern(f, pattern)] if os.path.exists(final_dir) else []
        files_to_delete = [os.path.join(final_dir, f) for f in matches]
        if not files_to_delete:
            run_async(clear_new_episode_flag(data[0]), on_done=lambda _: self._refresh_table())
            return
        ConfirmClearDialog(self, data[0], pattern, files_to_delete, len(matches), self.log, self._refresh_table)

    def _action_delete(self):
        selected = self.tree.selection()
        if not selected: return
        iid = selected[0]
        data = self._anime_data.get(iid)
        if not data: return
        def on_done(_):
            self.log(f"Anime '{data[6] or data[1]}' removido.", "orange")
            self.sidebar.clear()
            self._refresh_table()
        run_async(remove_anime(data[0]), on_done=on_done)

    def _action_edit_episode(self):
        selected = self.tree.selection()
        if not selected: return
        data = self._anime_data.get(selected[0])
        if not data: return
        EpisodeEditorDialog(self, data[0], data[6] or data[1], data[2], self.log, self._refresh_table)

    def _action_open_settings(self): SettingsDialog(self, self.log)
    def _action_open_folder(self): 
        os.makedirs(get_final_dir(), exist_ok=True)
        open_path(get_final_dir())

    def _action_download_subs(self): self._action_force_sub_selected()

    def _action_force_sub_selected(self):
        selected = self.tree.selection()
        if not selected: return
        data = self._anime_data.get(selected[0])
        if not data: return
        self.log(f"Buscando legendas para '{data[6] or data[1]}'...", "blue")
        def on_candidates(res):
            if res and not isinstance(res, Exception): self._process_subtitle_candidates(res)
        run_async(get_subtitle_candidates_for_anime(data[1]), on_done=on_candidates)

    def _process_subtitle_candidates(self, candidates):
        to_auto, to_select = [], []
        for c in candidates:
            if not c["subs"]: continue
            if len(c["subs"]) == 1: to_auto.append(c)
            else: to_select.append(c)
        for c in to_auto:
            run_async(download_chosen_subtitle(c["subs"][0], c["series_name"], c["ep_str"]), 
                      on_done=lambda path, p=c["pattern"], ep=c["ep_str"]: self._on_sub_downloaded(path, p, ep))
        if to_select:
            SubtitleQueueProcessor(self, to_select, self.log, self._on_sub_downloaded, self._action_organize).process_next()

    def _on_sub_downloaded(self, path, pattern, ep_str):
        if path and not isinstance(path, Exception):
            self.log(f"LEGENDA BAIXADA: {pattern} - Ep {int(ep_str)}", "green")
            self.sidebar.refresh_sub_status(pattern)

    def _add_anime(self):
        self.adder_logic.add_anime_by_name(self.entry.get().strip())

    def _action_refresh_selected_metadata(self):
        selected = self.tree.selection()
        if not selected: return
        data = self._anime_data.get(selected[0])
        if not data: return
        self.log(f"Buscando metadados...", "blue")
        run_async(refresh_single_metadata(data[0], data[1]), on_done=lambda _: (self.sidebar.clear_cache(), self._refresh_table()))

    def _show_context_menu(self, event):
        row = self.tree.identify_row(event.y)
        if not row: return
        self.tree.selection_set(row)
        menu = tk.Menu(self, tearoff=0, bg="#2a2a2a", fg="#ffffff", font=("Segoe UI", 10))
        menu.add_command(label="▶ Play", command=self._action_play)
        menu.add_command(label="📁 Abrir Pasta", command=self._action_open_folder)
        menu.add_separator()
        menu.add_command(label="✏ Editar Episódio", command=self._action_edit_episode)
        menu.add_command(label="🔄 Atualizar Metadados", command=self._action_refresh_selected_metadata)
        menu.add_command(label="🔍 Buscar Legenda", command=self._action_force_sub_selected)
        menu.add_separator()
        menu.add_command(label="✓ Marcar como Visto", command=self._action_mark_watched)
        menu.add_separator()
        menu.add_command(label="🗑 Remover da Lista", command=self._action_delete)
        menu.tk_popup(event.x_root, event.y_root)

    def _periodic_refresh(self):
        self._action_refresh()
        self.after(600_000, self._periodic_refresh)

    def _on_close(self):
        stop_loop(); self.destroy()
