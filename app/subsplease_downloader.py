import asyncio
import threading
from datetime import datetime
import tkinter as tk
from tkinter import ttk
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import init_db, get_monitored_animes, add_anime, remove_anime
from downloader import check_for_updates, search_anime_history, process_releases, organize_downloads, force_download_subs

# Event loop asyncio em daemon thread
_loop = asyncio.new_event_loop()
_loop_thread = threading.Thread(target=_loop.run_forever, daemon=True)
_loop_thread.start()


def run_async(coro, on_done=None):
    def _callback(future):
        try:
            result = future.result()
        except Exception as e:
            result = e
        if on_done:
            # Garante que on_done é chamado na thread principal do tkinter
            app_ref.after(0, lambda: on_done(result))

    future = asyncio.run_coroutine_threadsafe(coro, _loop)
    if on_done:
        future.add_done_callback(_callback)
    return future


app_ref = None  # Referência global para a janela principal (setado em main)


class AnimeMonitorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        global app_ref
        app_ref = self

        self.title("Anime Monitor")
        self.geometry("900x700")
        self.configure(bg="#1e1e1e")
        self.resizable(True, True)

        self._build_ui()
        self._apply_styles()

        # Inicializa o banco e carrega a tabela
        run_async(init_db(), on_done=lambda _: run_async(self._load_table_async(), on_done=self._on_table_loaded))

        # Refresh automático a cada 10 minutos
        self.after(600_000, self._periodic_refresh)

        # Dispara verificação inicial
        self.after(500, self._action_refresh)

    # ─── UI Build ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Tabela
        table_frame = tk.Frame(self, bg="#1e1e1e")
        table_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(8, 4))

        cols = ("ID", "Anime", "Último Ep", "Resolução")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", selectmode="browse")
        for col in cols:
            self.tree.heading(col, text=col)
        self.tree.column("ID", width=50, anchor=tk.CENTER)
        self.tree.column("Anime", width=400)
        self.tree.column("Último Ep", width=100, anchor=tk.CENTER)
        self.tree.column("Resolução", width=100, anchor=tk.CENTER)

        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        # Linha de input
        input_frame = tk.Frame(self, bg="#1e1e1e")
        input_frame.pack(fill=tk.X, padx=8, pady=4)

        self.entry = ttk.Entry(input_frame, font=("Segoe UI", 11))
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        self.entry.bind("<Return>", lambda e: self._add_anime())

        add_btn = ttk.Button(input_frame, text="Adicionar", command=self._add_anime)
        add_btn.pack(side=tk.LEFT, padx=(8, 0))

        # Linha de ações
        action_frame = tk.Frame(self, bg="#1e1e1e")
        action_frame.pack(fill=tk.X, padx=8, pady=4)

        ttk.Button(action_frame, text="Verificar Agora", command=self._action_refresh).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(action_frame, text="Organizar", command=self._action_organize).pack(side=tk.LEFT, padx=4)
        ttk.Button(action_frame, text="Buscar Legendas", command=self._action_download_subs).pack(side=tk.LEFT, padx=4)
        ttk.Button(action_frame, text="Remover Selecionado", command=self._action_delete).pack(side=tk.LEFT, padx=4)

        # Log
        log_label = tk.Label(self, text="Log de Atividade", bg="#1e1e1e", fg="#888888", font=("Segoe UI", 9))
        log_label.pack(anchor=tk.W, padx=10)

        log_frame = tk.Frame(self, bg="#000000", relief=tk.SUNKEN, bd=1)
        log_frame.pack(fill=tk.BOTH, expand=False, padx=8, pady=(0, 8))
        log_frame.pack_propagate(False)
        log_frame.configure(height=200)

        self.log_text = tk.Text(
            log_frame, bg="#000000", fg="#ffffff", font=("Consolas", 9),
            state=tk.DISABLED, wrap=tk.WORD, bd=0, highlightthickness=0
        )
        log_vsb = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_vsb.set)
        log_vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._configure_log_tags()

    def _apply_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Treeview", background="#2a2a2a", foreground="#ffffff",
                        fieldbackground="#2a2a2a", rowheight=24, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", background="#333333", foreground="#ffffff",
                        font=("Segoe UI", 10, "bold"))
        style.map("Treeview", background=[("selected", "#1565c0")])
        style.configure("TEntry", fieldbackground="#2a2a2a", foreground="#ffffff",
                        insertcolor="#ffffff")
        style.configure("TButton", background="#333333", foreground="#ffffff",
                        font=("Segoe UI", 10), padding=6)
        style.map("TButton", background=[("active", "#444444")])
        style.configure("TScrollbar", background="#333333", troughcolor="#1e1e1e",
                        arrowcolor="#ffffff")

    def _configure_log_tags(self):
        colors = {
            "green": "#4caf50", "red": "#f44336", "cyan": "#00bcd4",
            "yellow": "#ffeb3b", "blue": "#2196f3", "orange": "#ff9800",
            "white": "#ffffff",
        }
        for name, color in colors.items():
            self.log_text.tag_configure(name, foreground=color)

    # ─── Log ──────────────────────────────────────────────────────────────────

    def log(self, message: str, color: str = "white"):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{ts}] ", "white")
        self.log_text.insert(tk.END, message + "\n", color)
        self.log_text.configure(state=tk.DISABLED)
        self.log_text.see(tk.END)

    # ─── Table ────────────────────────────────────────────────────────────────

    async def _load_table_async(self):
        return await get_monitored_animes()

    def _on_table_loaded(self, animes):
        if isinstance(animes, Exception):
            self.log(f"Erro ao carregar tabela: {animes}", "red")
            return
        for row in self.tree.get_children():
            self.tree.delete(row)
        for anime in animes:
            self.tree.insert("", tk.END, values=[str(x) for x in anime])

    def _refresh_table(self):
        run_async(self._load_table_async(), on_done=self._on_table_loaded)

    # ─── Actions ──────────────────────────────────────────────────────────────

    def _action_refresh(self):
        self.log("Verificando novas releases...", "blue")

        def on_done(result):
            if isinstance(result, Exception):
                self.log(f"Erro na verificação: {result}", "red")
                return
            if result:
                for item in result:
                    self.log(f"DOWNLOAD INICIADO: {item}", "green")
                self._refresh_table()
            else:
                self.log("Nenhuma release nova encontrada.", "yellow")
            self._run_organize_logic()

        run_async(check_for_updates(), on_done=on_done)

    def _action_organize(self):
        self._run_organize_logic()

    def _run_organize_logic(self):
        self.log("Organizando arquivos finalizados...", "blue")

        def on_done(result):
            if isinstance(result, Exception):
                self.log(f"Erro ao organizar: {result}", "red")
                return
            if result:
                for f in result:
                    self.log(f"ORGANIZADO: {f}", "cyan")
            else:
                self.log("Nada pendente para organizar.", "yellow")

        run_async(organize_downloads(), on_done=on_done)

    def _action_download_subs(self):
        self.log("Buscando legendas para os episódios atuais...", "blue")

        def on_done(result):
            if isinstance(result, Exception):
                self.log(f"Erro ao buscar legendas: {result}", "red")
                return
            if result:
                for item in result:
                    self.log(f"LEGENDA BAIXADA: {item}", "green")
                self._run_organize_logic()
            else:
                self.log("Nenhuma legenda nova encontrada.", "yellow")

        run_async(force_download_subs(), on_done=on_done)

    def _action_delete(self):
        selected = self.tree.selection()
        if not selected:
            self.log("Nenhum anime selecionado para remover.", "red")
            return
        values = self.tree.item(selected[0], "values")
        anime_id = int(values[0])
        anime_name = values[1]

        def on_done(_):
            self.log(f"Anime '{anime_name}' removido.", "orange")
            self._refresh_table()

        run_async(remove_anime(anime_id), on_done=on_done)

    def _periodic_refresh(self):
        self._action_refresh()
        self.after(600_000, self._periodic_refresh)

    # ─── Add Anime ────────────────────────────────────────────────────────────

    def _add_anime(self):
        raw = self.entry.get().strip()

        if not raw:
            self.log("Digite o nome do anime antes de adicionar.", "red")
            return

        # Formato "nome:ep" — comportamento direto sem diálogo
        if ":" in raw:
            parts = raw.rsplit(":", 1)
            name = parts[0].strip()
            try:
                start_ep = int(parts[1].strip())
            except ValueError:
                start_ep = 0
            self._confirm_add(name, start_ep, history=None)
            return

        # Sem episódio — buscar histórico para mostrar diálogo
        name = raw
        self.log(f"Buscando histórico de '{name}'...", "blue")

        def on_history(result):
            if isinstance(result, Exception):
                self.log(f"Erro ao buscar histórico: {result}", "red")
                history = None
                max_ep = 0
            else:
                history = list(result) if result else []
                max_ep = 0
                for item in history:
                    info = item[1] if isinstance(item, tuple) else item
                    try:
                        ep = int(info.get("episode", 0))
                        if ep > max_ep:
                            max_ep = ep
                    except (TypeError, ValueError):
                        pass

            self._show_episode_dialog(name, max_ep, history)

        run_async(search_anime_history(name), on_done=on_history)

    def _show_episode_dialog(self, name: str, max_ep: int, history):
        dialog = tk.Toplevel(self)
        dialog.title(name)
        dialog.configure(bg="#1e1e1e")
        dialog.resizable(False, False)
        dialog.grab_set()  # modal

        # Centraliza sobre a janela principal
        self.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 340) // 2
        y = self.winfo_y() + (self.winfo_height() - 160) // 2
        dialog.geometry(f"340x160+{x}+{y}")

        ep_count_msg = f"{max_ep} episódios encontrados." if max_ep > 0 else "Nenhum episódio encontrado no histórico."
        tk.Label(dialog, text=ep_count_msg, bg="#1e1e1e", fg="#ffffff",
                 font=("Segoe UI", 10)).pack(pady=(16, 4))
        tk.Label(dialog, text="A partir de qual episódio deseja baixar?",
                 bg="#1e1e1e", fg="#aaaaaa", font=("Segoe UI", 9)).pack()

        initial = max(0, max_ep - 2) if max_ep > 0 else 0
        spinbox = ttk.Spinbox(dialog, from_=0, to=max(max_ep, 9999), width=10,
                              font=("Segoe UI", 11))
        spinbox.set(initial)
        spinbox.pack(pady=8)

        btn_frame = tk.Frame(dialog, bg="#1e1e1e")
        btn_frame.pack(pady=4)

        chosen = {"ep": None}

        def confirm():
            try:
                chosen["ep"] = int(spinbox.get())
            except ValueError:
                chosen["ep"] = 0
            dialog.destroy()

        def cancel():
            dialog.destroy()

        ttk.Button(btn_frame, text="Confirmar", command=confirm).pack(side=tk.LEFT, padx=8)
        ttk.Button(btn_frame, text="Cancelar", command=cancel).pack(side=tk.LEFT, padx=8)

        dialog.bind("<Return>", lambda e: confirm())
        dialog.bind("<Escape>", lambda e: cancel())

        dialog.wait_window()

        if chosen["ep"] is not None:
            self._confirm_add(name, chosen["ep"], history)

    def _confirm_add(self, name: str, start_ep: int, history):
        def on_added(result):
            if isinstance(result, Exception):
                self.log(f"Erro ao adicionar: {result}", "red")
                return
            if not result:
                self.log(f"Erro: '{name}' já está na lista ou erro no banco.", "red")
                return

            self.log(f"Adicionado: {name} (iniciando após Ep {start_ep})", "cyan")
            self.entry.delete(0, tk.END)
            self._refresh_table()

            if history:
                def on_releases(releases):
                    if isinstance(releases, Exception):
                        self.log(f"Erro ao processar histórico: {releases}", "red")
                        return
                    if releases:
                        for item in releases:
                            self.log(f"DOWNLOAD HISTÓRICO: {item}", "green")
                        self._refresh_table()
                    else:
                        self.log("Nenhum episódio novo encontrado no histórico.", "yellow")
                run_async(process_releases(history), on_done=on_releases)
            else:
                self.log("Histórico não encontrado. Verificando feed geral...", "yellow")
                self._action_refresh()

        run_async(add_anime(name, start_episode=start_ep), on_done=on_added)


if __name__ == "__main__":
    app = AnimeMonitorApp()
    app.mainloop()
