import asyncio
import os
import tkinter as tk
from tkinter import ttk
from ...core.downloader import get_final_dir, matches_pattern
from ...core.database import set_last_episode, clear_new_episode_flag
from ...core.config import should_delete_on_watched
from ...utils.async_bridge import run_async
from ...utils.episode_parser import extract_episode_number

class WatchedSelectorDialog(tk.Toplevel):
    def __init__(self, parent, anime_id, pattern, anime_name, matches, log_callback, refresh_callback):
        super().__init__(parent)
        self.parent = parent
        self.anime_id = anime_id
        self.pattern = pattern
        self.anime_name = anime_name
        self.matches = matches  # lista de nomes de arquivos
        self.log_callback = log_callback
        self.refresh_callback = refresh_callback

        self.title(f"Marcar Visto - {anime_name}")
        self.geometry("500x450")
        self.configure(bg="#1e1e1e")
        self.transient(parent)
        self.grab_set()

        self._center_dialog()
        self._build_ui()

    def _center_dialog(self):
        self.update_idletasks()
        x = self.parent.winfo_x() + (self.parent.winfo_width() // 2) - (self.winfo_width() // 2)
        y = self.parent.winfo_y() + (self.parent.winfo_height() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")

    def _extract_ep_num(self, filename):
        return extract_episode_number(filename) or 0

    def _build_ui(self):
        tk.Label(self, text="Selecione os episódios que você já assistiu:", 
                 bg="#1e1e1e", fg="#ffffff", font=("Segoe UI", 10, "bold")).pack(pady=10)

        frame = tk.Frame(self, bg="#1e1e1e")
        frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)

        # Usar Checkboxes em uma lista scrollable
        canvas = tk.Canvas(frame, bg="#1e1e1e", highlightthickness=0)
        vsb = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        self.scrollable_frame = tk.Frame(canvas, bg="#1e1e1e")

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=vsb.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self.check_vars = {}
        # Ordenar por número de episódio
        sorted_matches = sorted(self.matches, key=self._extract_ep_num)

        for filename in sorted_matches:
            var = tk.BooleanVar(value=False)
            self.check_vars[filename] = var
            
            row = tk.Frame(self.scrollable_frame, bg="#1e1e1e")
            row.pack(fill=tk.X, pady=2)
            
            cb = tk.Checkbutton(row, text=filename, variable=var, bg="#1e1e1e", fg="#ffffff", 
                               selectcolor="#1e1e1e", activebackground="#1e1e1e", activeforeground="#ffffff")
            cb.pack(side=tk.LEFT, anchor=tk.W)

        btn_frame = tk.Frame(self, bg="#1e1e1e")
        btn_frame.pack(pady=15)
        
        ttk.Button(btn_frame, text="Confirmar", command=self._confirm).pack(side=tk.LEFT, padx=8)
        ttk.Button(btn_frame, text="Cancelar", command=self.destroy).pack(side=tk.LEFT, padx=8)

    def _confirm(self):
        selected_files = [f for f, var in self.check_vars.items() if var.get()]
        if not selected_files:
            self.destroy()
            return

        delete_on_watched = should_delete_on_watched()
        final_dir = get_final_dir()
        anime_id = self.anime_id
        log_cb = self.log_callback
        refresh_cb = self.refresh_callback

        async def do_all():
            final_files = await asyncio.to_thread(os.listdir, final_dir)

            max_watched = 0
            files_to_delete = []
            for f in selected_files:
                ep_num = extract_episode_number(f) or 0
                if ep_num > max_watched:
                    max_watched = ep_num
                files_to_delete.append(os.path.join(final_dir, f))
                name_no_ext = os.path.splitext(f)[0]
                for ext_file in final_files:
                    if ext_file.startswith(name_no_ext) and ext_file.lower().endswith((".ass", ".srt")):
                        files_to_delete.append(os.path.join(final_dir, ext_file))

            await set_last_episode(anime_id, max_watched)
            await clear_new_episode_flag(anime_id)

            deleted_count = 0
            if delete_on_watched:
                for path in files_to_delete:
                    try:
                        if os.path.exists(path):
                            await asyncio.to_thread(os.remove, path)
                            deleted_count += 1
                    except Exception as e:
                        print(f"Erro ao deletar {path}: {e}")

            return max_watched, deleted_count

        def on_done(result):
            if isinstance(result, Exception):
                if log_cb:
                    log_cb("Erro ao marcar como visto.", "red")
            else:
                max_watched, deleted_count = result
                if delete_on_watched:
                    if log_cb:
                        log_cb(f"Assistidos marcados. {deleted_count} arquivo(s) removidos.", "cyan")
                else:
                    if log_cb:
                        log_cb(f"Assistidos marcados (arquivos mantidos). Novo status: Ep {max_watched}", "cyan")
            refresh_cb()
            try:
                self.destroy()
            except Exception:
                pass

        run_async(do_all(), on_done=on_done)
