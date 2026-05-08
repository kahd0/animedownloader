import asyncio
import os
import re
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime

from ..core.config import (
    STATUS_PT, get_final_dir, VERSION, GITHUB_REPO,
    get_check_interval, is_auto_organize_enabled
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
from ..utils.episode_parser import extract_episode_number
from ..utils.updater import download_file, apply_update_and_restart

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
from .dialogs.feedback_dialog import FeedbackDialog
from .dialogs.watched_selector import WatchedSelectorDialog
from .dialogs.error_reporter import show_error_dialog

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
        self._periodic_refresh_id = None

        self._build_ui()
        self._apply_custom_styles()
        
        self.adder_logic = AnimeAdderLogic(self, self.log, self._refresh_table)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        run_async(init_db(), on_done=lambda _: run_async(
            self._load_table_async(), on_done=self._on_table_loaded
        ))
        self.update_check_timer()
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
        ttk.Button(action_frame, text="⚑ Relatar Problema", command=self._action_report_feedback).pack(side=tk.LEFT, padx=4)

        # Log Component
        self.activity_log = ActivityLog(self, height=180)
        self.activity_log.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(0, 8))

    def log(self, message: str, color: str = "white"):
        self.activity_log.log(message, color)

    def _check_app_updates(self):
        import sys

        def _parse_version(tag: str):
            import re
            nums = re.findall(r'\d+', tag)
            return tuple(int(n) for n in nums)

        def on_checked(update):
            if isinstance(update, Exception) or not update:
                return
            remote = update["tag_name"]
            if _parse_version(remote) <= _parse_version(VERSION):
                return

            is_frozen = getattr(sys, "frozen", False)
            has_asset = bool(update.get("asset_url")) and is_frozen

            if has_asset:
                if messagebox.askyesno(
                    "Nova Versão Disponível",
                    f"Versão {update['tag_name']} disponível!\nAtualizar automaticamente? (o app será reiniciado)"
                ):
                    self._apply_auto_update(update)
                return

            if messagebox.askyesno(
                "Nova Versão Disponível",
                f"Versão {update['tag_name']} disponível!\nAbrir página de download?"
            ):
                import webbrowser
                webbrowser.open(update["html_url"])

        run_async(check_for_app_updates(GITHUB_REPO), on_done=on_checked)

    def _apply_auto_update(self, update):
        import tempfile
        tmp_path = os.path.join(tempfile.gettempdir(), update.get("file_name", "anime_monitor_update"))
        self.log(f"Baixando atualização v{update['tag_name']}...", "blue")

        def on_downloaded(ok):
            if isinstance(ok, Exception) or not ok:
                self.log("Falha no download da atualização.", "red")
                return
            self.log("Download concluído. Reiniciando...", "green")
            apply_update_and_restart(tmp_path)

        run_async(download_file(update["asset_url"], tmp_path), on_done=on_downloaded)

    async def _load_table_async(self):
        animes = await get_monitored_animes()
        final_dir = get_final_dir()
        episode_map: dict[str, int] = {}
        if os.path.exists(final_dir):
            def _scan():
                em: dict[str, int] = {}
                try:
                    for f in os.listdir(final_dir):
                        if not f.lower().endswith((".mkv", ".mp4")):
                            continue
                        ep = extract_episode_number(f)
                        if ep is None:
                            continue
                        for anime in animes:
                            if matches_pattern(f, anime[1]):
                                key = anime[1].lower()
                                if em.get(key, 0) < ep:
                                    em[key] = ep
                except OSError:
                    pass
                return em
            episode_map = await asyncio.to_thread(_scan)
        return animes, episode_map

    def _on_table_loaded(self, result):
        if isinstance(result, Exception):
            self.log(f"Erro ao carregar tabela: {result}", "red")
            return
        animes, episode_map = result
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

            watched_ep = anime[2]
            local_max = episode_map.get(anime[1].lower(), watched_ep)
            ep_display = f"{watched_ep} / {local_max}" if local_max > watched_ep else str(watched_ep)

            tags = []
            if status_raw == "Currently Airing": tags.append("airing")
            elif status_raw == "Finished Airing": tags.append("finished")
            elif status_raw == "Not yet aired": tags.append("upcoming")
            if has_new: tags.append("new_ep")

            self.tree.insert("", tk.END, iid=iid, tags=tags, values=[
                str(anime[0]), ("🔥 " if has_new else "") + display_title,
                ep_display, str(anime[3]), anime[4] or "—", status_pt,
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
            
            if is_auto_organize_enabled():
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
        pattern = data[1]
        final_dir = get_final_dir()
        if not os.path.exists(final_dir): return

        def _find():
            return [f for f in os.listdir(final_dir)
                    if f.lower().endswith((".mkv", ".mp4")) and matches_pattern(f, pattern)]

        def on_found(result):
            if isinstance(result, Exception) or not result:
                self.log(f"Nenhum episódio encontrado para '{pattern}'.", "yellow")
                return
            if len(result) == 1:
                open_path(os.path.join(final_dir, result[0]))
            else:
                PlaySelectorDialog(self, data[6] or data[1], result, self.log)

        run_async(asyncio.to_thread(_find), on_done=on_found)

    def _action_mark_watched(self):
        selected = self.tree.selection()
        if not selected: return
        iid = selected[0]
        data = self._anime_data.get(iid)
        if not data: return
        anime_id, pattern = data[0], data[1]
        anime_name = data[6] or data[1]
        final_dir = get_final_dir()

        def _scan():
            if not os.path.exists(final_dir):
                return []
            return [f for f in os.listdir(final_dir)
                    if f.lower().endswith((".mkv", ".mp4")) and matches_pattern(f, pattern)]

        def on_scanned(result):
            if isinstance(result, Exception):
                result = []
            if not result:
                self.log(f"Nenhum arquivo local para '{anime_name}'. Flag limpa.", "yellow")
                run_async(clear_new_episode_flag(anime_id), on_done=lambda _: self._refresh_table())
                return
            WatchedSelectorDialog(
                self, anime_id, pattern, anime_name, result,
                self.log, self._refresh_table
            )

        run_async(asyncio.to_thread(_scan), on_done=on_scanned)

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
    def _action_report_feedback(self): FeedbackDialog(self)
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
        _running = [True]
        _elapsed = [0]
        def _ping():
            if _running[0]:
                _elapsed[0] += 10
                self.log(f"Ainda buscando... ({_elapsed[0]}s)", "blue")
                self.after(10000, _ping)
        self.after(10000, _ping)
        def on_candidates(res):
            _running[0] = False
            if isinstance(res, Exception):
                self.log(f"Erro ao buscar legendas: {res}", "red")
            elif res:
                self._process_subtitle_candidates(res)
            else:
                self.log("Nenhum episódio sem legenda encontrado.", "yellow")
        run_async(get_subtitle_candidates_for_anime(data[1]), on_done=on_candidates)

    def _process_subtitle_candidates(self, candidates):
        with_subs = [c for c in candidates if c["subs"]]
        for c in candidates:
            if not c["subs"]:
                self.log(f"Nenhuma legenda encontrada: {c['pattern']} - Ep {c['last_ep']}", "yellow")
            else:
                self.log(f"{len(c['subs'])} legenda(s) encontrada(s): {c['pattern']} - Ep {c['last_ep']}", "blue")
        if with_subs:
            SubtitleQueueProcessor(self, with_subs, self.log, self._on_sub_downloaded, self._action_organize).process_next()

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

    def update_check_timer(self):
        if self._periodic_refresh_id:
            self.after_cancel(self._periodic_refresh_id)
        
        interval = get_check_interval()
        self._periodic_refresh_id = self.after(interval, self._periodic_refresh)

    def _periodic_refresh(self):
        self._action_refresh()
        self.update_check_timer()

    def report_callback_exception(self, exc_type, exc_value, exc_tb):
        exc_value.__traceback__ = exc_tb
        show_error_dialog(self, exc_value, "Erro na interface")

    def _on_close(self):
        stop_loop(); self.destroy()
