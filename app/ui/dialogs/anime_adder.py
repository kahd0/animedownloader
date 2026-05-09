import tkinter as tk
from tkinter import ttk
from ...core.config import get_default_resolution
from ...core.api import search_anime_history, fetch_anime_metadata
from ...core.database import add_anime, update_anime_metadata, get_monitored_animes
from ...core.downloader import process_releases
from ...utils.async_bridge import run_async

class AnimeAdderLogic:
    def __init__(self, parent, log_callback, refresh_callback):
        self.parent = parent
        self.log_callback = log_callback
        self.refresh_callback = refresh_callback

    def add_anime_by_name(self, raw_name):
        if not raw_name:
            self.log_callback("Digite o nome do anime antes de adicionar.", "red")
            return
            
        self.log_callback(f"Buscando histórico de '{raw_name}'...", "blue")
        
        def on_history(result):
            if isinstance(result, Exception):
                self.log_callback(f"Erro ao buscar histórico: {result}", "red")
                history, max_ep, min_ep, feed_name = None, 0, 0, raw_name
            else:
                history = list(result) if result else []
                max_ep, min_ep, feed_counts = 0, 0, {}
                eps = []
                for item in history:
                    info = item[1] if isinstance(item, tuple) else item
                    fn = info.get('show', '') if isinstance(info, dict) else ""
                    if fn: feed_counts[fn] = feed_counts.get(fn, 0) + 1
                    try:
                        ep = int(info.get("episode", 0))
                        if ep > 0: eps.append(ep)
                        max_ep = max(max_ep, ep)
                    except: pass
                min_ep = min(eps) if eps else 0
                feed_name = max(feed_counts, key=feed_counts.get) if feed_counts else raw_name

            self._show_episode_dialog(raw_name, max_ep, min_ep, history, feed_name)
            
        run_async(search_anime_history(raw_name), on_done=on_history)

    def _show_episode_dialog(self, name: str, max_ep: int, min_ep: int, history, feed_name: str = ""):
        feed_name = feed_name or name
        dialog = tk.Toplevel(self.parent)
        dialog.title(feed_name)
        dialog.configure(bg="#121212")

        has_feed_label = feed_name != name
        has_range = min_ep > 0 and max_ep > 0
        h = 160 + (25 if has_feed_label else 0) + (30 if has_range else 0)
        w = 340
        self.parent.update_idletasks()
        x = self.parent.winfo_x() + (self.parent.winfo_width() - w) // 2
        y = self.parent.winfo_y() + (self.parent.winfo_height() - h) // 2
        dialog.geometry(f"{w}x{h}+{x}+{y}")
        dialog.transient(self.parent)
        dialog.grab_set()

        if has_feed_label:
            tk.Label(dialog, text=f"Feed: {feed_name}", bg="#121212", fg="#4ec9b0",
                     font=("Segoe UI", 9), wraplength=310).pack(pady=(12, 0))

        tk.Label(dialog, text=f"Último episódio no histórico: {max_ep}." if max_ep > 0 else "Nenhum histórico encontrado.",
                 bg="#121212", fg="#ffffff", font=("Segoe UI", 10)).pack(pady=(8, 4))

        spinbox = ttk.Spinbox(dialog, from_=0, to=max(max_ep, 9999), width=10, font=("Segoe UI", 11))
        spinbox.set(max(0, max_ep - 2) if max_ep > 0 else 0)
        spinbox.pack(pady=8)

        if has_range:
            tk.Label(dialog, text=f"⚠ Histórico disponível: ep {min_ep} – {max_ep}",
                     bg="#121212", fg="#f0a500", font=("Segoe UI", 8)).pack(pady=(0, 4))
        
        chosen = {"ep": None}
        def confirm():
            try: chosen["ep"] = int(spinbox.get())
            except: chosen["ep"] = 0
            dialog.destroy()
            
        btn_frame = tk.Frame(dialog, bg="#121212")
        btn_frame.pack(pady=4)
        ttk.Button(btn_frame, text="Confirmar", command=confirm).pack(side=tk.LEFT, padx=8)
        ttk.Button(btn_frame, text="Cancelar", command=dialog.destroy).pack(side=tk.LEFT, padx=8)
        
        dialog.wait_window()
        if chosen["ep"] is not None: 
            self._confirm_add(feed_name, chosen["ep"], history)

    def _confirm_add(self, name: str, start_ep: int, history):
        def on_added(result):
            if isinstance(result, Exception):
                self.log_callback(f"Erro ao adicionar: {result}", "red")
                return
            if not result:
                self.log_callback(f"Erro: '{name}' já está na lista ou erro no banco.", "red")
                return
                
            self.log_callback(f"Adicionado: {name} (após Ep {start_ep})", "cyan")
            self.refresh_callback()
            self._fetch_metadata_for(name)
            
            if history:
                def on_releases(releases):
                    if isinstance(releases, Exception):
                        self.log_callback(f"Erro ao processar: {releases}", "red")
                        return
                    if releases:
                        for item in releases:
                            self.log_callback(f"DOWNLOAD HISTÓRICO: {item}", "green")
                        self.refresh_callback()
                    else:
                        self.log_callback("Nenhum episódio novo no histórico.", "yellow")
                run_async(process_releases(history), on_done=on_releases)
            else:
                self.log_callback("Histórico não encontrado. Verificando feed...", "yellow")
                # Trigger a global check
                self.parent.after(100, lambda: self.parent._action_refresh())
                
        run_async(add_anime(name, resolution=get_default_resolution(), start_episode=start_ep), on_done=on_added)

    def _fetch_metadata_for(self, title_pattern: str):
        async def _task():
            animes = await get_monitored_animes()
            row = next((a for a in animes if a[1] == title_pattern), None)
            if not row: return
            meta = await fetch_anime_metadata(title_pattern)
            if not meta: return
            await update_anime_metadata(row[0], meta["official_title"], meta["cover_url"], meta["airing_status"])
            return await self.parent._load_table_async()
            
        def on_meta_done(res):
            if res and not isinstance(res, Exception):
                self.parent._on_table_loaded(res)
                
        run_async(_task(), on_done=on_meta_done)
