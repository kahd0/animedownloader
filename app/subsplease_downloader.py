import asyncio
import threading
from datetime import datetime
import tkinter as tk
from tkinter import ttk
import sys
import os
import re
import pystray
from PIL import Image, ImageDraw, ImageTk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import (
    init_db, get_monitored_animes, add_anime, remove_anime,
    update_anime_metadata, clear_new_episode_flag,
)
from downloader import (
    check_for_updates, search_anime_history, process_releases,
    organize_downloads, force_download_subs, open_path,
    FINAL_DIR, search_jikan, fetch_anime_metadata, download_cover,
    get_subtitle_candidates, download_chosen_subtitle, check_subtitle_status,
    refresh_single_metadata, refresh_all_metadata, COVERS_DIR, find_subtitles,
)
from database import set_last_episode

# ─── Async bridge ─────────────────────────────────────────────────────────────

_loop = asyncio.new_event_loop()
threading.Thread(target=_loop.run_forever, daemon=True).start()

app_ref = None


def run_async(coro, on_done=None):
    def _callback(future):
        try:
            result = future.result()
        except Exception as e:
            result = e
        if on_done:
            app_ref.after(0, lambda: on_done(result))

    future = asyncio.run_coroutine_threadsafe(coro, _loop)
    if on_done:
        future.add_done_callback(_callback)
    return future


# ─── Status helpers ───────────────────────────────────────────────────────────

STATUS_COLORS = {
    "Currently Airing": "#4caf50",
    "Finished Airing":  "#888888",
    "Not yet aired":    "#2196f3",
}
STATUS_PT = {
    "Currently Airing": "Em Exibição",
    "Finished Airing":  "Finalizado",
    "Not yet aired":    "Em Breve",
}

COVER_W, COVER_H = 140, 200  # sidebar thumbnail size


class AnimeMonitorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        global app_ref
        app_ref = self

        self.title("Anime Monitor")
        self.geometry("1060x700")
        self.configure(bg="#1e1e1e")
        self.resizable(True, True)

        self._anime_data: dict = {}      # iid (str) → full DB tuple
        self._cover_cache: dict = {}     # iid → ImageTk.PhotoImage (prevents GC)
        self._suggest_after_id = None
        self._suggest_popup = None
        self._current_sidebar_iid = None

        self._build_ui()
        self._apply_styles()

        self.protocol("WM_DELETE_WINDOW", self._hide_to_tray)
        self._tray_icon = None
        self._start_tray()

        run_async(init_db(), on_done=lambda _: run_async(
            self._load_table_async(), on_done=self._on_table_loaded
        ))
        self.after(600_000, self._periodic_refresh)
        self.after(500, self._action_refresh)

    # ─── System Tray ──────────────────────────────────────────────────────────

    def _make_tray_image(self):
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse([4, 4, 60, 60], fill="#1e1e1e", outline="#4caf50", width=4)
        d.polygon([(22, 18), (22, 46), (48, 32)], fill="#4caf50")
        return img

    def _start_tray(self):
        menu = pystray.Menu(
            pystray.MenuItem("Mostrar", self._show_window, default=True),
            pystray.MenuItem("Verificar Agora", lambda: self.after(0, self._action_refresh)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Sair", self._quit_app),
        )
        self._tray_icon = pystray.Icon("anime_monitor", self._make_tray_image(), "Anime Monitor", menu)
        threading.Thread(target=self._tray_icon.run, daemon=True).start()

    def _hide_to_tray(self):
        self.withdraw()

    def _show_window(self):
        self.after(0, self._do_show_window)

    def _do_show_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def _quit_app(self):
        if self._tray_icon:
            self._tray_icon.stop()
        self.after(0, self.destroy)

    def notify(self, title: str, message: str):
        try:
            self._tray_icon.notify(message, title)
        except Exception:
            try:
                import subprocess as _sp
                _sp.run(["notify-send", title, message], check=False)
            except Exception:
                pass

    # ─── UI Build ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Área superior: tabela (esquerda) + sidebar (direita)
        top_frame = tk.Frame(self, bg="#1e1e1e")
        top_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(8, 4))

        # Tabela
        table_frame = tk.Frame(top_frame, bg="#1e1e1e")
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

        # Sidebar
        self._build_sidebar(top_frame)

        # Linha de input
        input_frame = tk.Frame(self, bg="#1e1e1e")
        input_frame.pack(fill=tk.X, padx=8, pady=4)

        self.entry = ttk.Entry(input_frame, font=("Segoe UI", 11))
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        self.entry.bind("<Return>", lambda e: self._add_anime())
        self.entry.bind("<KeyRelease>", self._on_entry_key)
        self.entry.bind("<FocusOut>", lambda e: self.after(150, self._close_suggestions))

        ttk.Button(input_frame, text="Adicionar", command=self._add_anime).pack(side=tk.LEFT, padx=(8, 0))

        # Linha de ações
        action_frame = tk.Frame(self, bg="#1e1e1e")
        action_frame.pack(fill=tk.X, padx=8, pady=4)

        ttk.Button(action_frame, text="Verificar Agora",    command=self._action_refresh).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(action_frame, text="Organizar",          command=self._action_organize).pack(side=tk.LEFT, padx=4)
        ttk.Button(action_frame, text="Buscar Legendas",    command=self._action_download_subs).pack(side=tk.LEFT, padx=4)
        ttk.Button(action_frame, text="Remover Selecionado",command=self._action_delete).pack(side=tk.LEFT, padx=4)
        ttk.Button(action_frame, text="▶ Play",             command=self._action_play).pack(side=tk.LEFT, padx=4)
        ttk.Button(action_frame, text="📁 Abrir Pasta",     command=self._action_open_folder).pack(side=tk.LEFT, padx=4)
        ttk.Button(action_frame, text="🔄 Metadados",       command=self._action_refresh_all_metadata).pack(side=tk.LEFT, padx=4)

        # Log
        tk.Label(self, text="Log de Atividade", bg="#1e1e1e", fg="#888888",
                 font=("Segoe UI", 9)).pack(anchor=tk.W, padx=10)

        log_frame = tk.Frame(self, bg="#000000", relief=tk.SUNKEN, bd=1)
        log_frame.pack(fill=tk.BOTH, expand=False, padx=8, pady=(0, 8))
        log_frame.pack_propagate(False)
        log_frame.configure(height=180)

        self.log_text = tk.Text(
            log_frame, bg="#000000", fg="#ffffff", font=("Consolas", 9),
            state=tk.DISABLED, wrap=tk.WORD, bd=0, highlightthickness=0,
        )
        log_vsb = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_vsb.set)
        log_vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._configure_log_tags()

    def _build_sidebar(self, parent):
        self.sidebar = tk.Frame(parent, bg="#252525", width=170)
        self.sidebar.pack(side=tk.RIGHT, fill=tk.Y, padx=(6, 0))
        self.sidebar.pack_propagate(False)

        # Capa (clicável para ampliar)
        self.cover_label = tk.Label(self.sidebar, bg="#252525", cursor="hand2")
        self.cover_label.pack(pady=(12, 6))
        self.cover_label.bind("<Button-1>", self._on_cover_click)
        self._set_placeholder_cover()

        # Título oficial
        self.sidebar_title = tk.Label(
            self.sidebar, text="—", bg="#252525", fg="#ffffff",
            font=("Segoe UI", 9, "bold"), wraplength=155, justify=tk.CENTER,
        )
        self.sidebar_title.pack(padx=6, pady=(0, 4))

        # Badge de status
        self.sidebar_status = tk.Label(
            self.sidebar, text="", bg="#252525", fg="#888888",
            font=("Segoe UI", 9), wraplength=155, justify=tk.CENTER,
        )
        self.sidebar_status.pack(padx=6)

        # Badge "NOVO"
        self.sidebar_new_badge = tk.Label(
            self.sidebar, text="", bg="#252525", fg="#ff9800",
            font=("Segoe UI", 9, "bold"),
        )
        self.sidebar_new_badge.pack(pady=(4, 0))

        # Status da legenda do último episódio
        ttk.Separator(self.sidebar, orient="horizontal").pack(fill=tk.X, padx=8, pady=(10, 4))
        tk.Label(self.sidebar, text="Legenda", bg="#252525", fg="#555555",
                 font=("Segoe UI", 8)).pack()
        self.sidebar_sub_status = tk.Label(
            self.sidebar, text="", bg="#252525", fg="#888888",
            font=("Segoe UI", 8), wraplength=155, justify=tk.CENTER,
        )
        self.sidebar_sub_status.pack(padx=6, pady=(2, 0))

    def _set_placeholder_cover(self):
        img = Image.new("RGB", (COVER_W, COVER_H), "#333333")
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, COVER_W - 1, COVER_H - 1], outline="#555555", width=2)
        ref = ImageTk.PhotoImage(img)
        self.cover_label.configure(image=ref)
        self.cover_label.image = ref

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

        # Tags de linha para status e "novo"
        self.tree.tag_configure("airing",   foreground="#4caf50")
        self.tree.tag_configure("finished", foreground="#888888")
        self.tree.tag_configure("upcoming", foreground="#2196f3")
        self.tree.tag_configure("new_ep",   background="#1b3328")

    def _configure_log_tags(self):
        colors = {
            "green": "#4caf50", "red": "#f44336", "cyan": "#00bcd4",
            "yellow": "#ffeb3b", "blue": "#2196f3", "orange": "#ff9800", "white": "#ffffff",
        }
        for name, color in colors.items():
            self.log_text.tag_configure(name, foreground=color)

    # ─── Dialog helper ────────────────────────────────────────────────────────

    def _center_dialog(self, dialog, w, h):
        """Centraliza, posiciona e ativa o grab de um Toplevel de forma segura."""
        self.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - w) // 2
        y = self.winfo_y() + (self.winfo_height() - h) // 2
        dialog.geometry(f"{w}x{h}+{x}+{y}")
        dialog.transient(self)
        dialog.update()          # força o mapeamento da janela antes do grab
        dialog.grab_set()

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
        self._anime_data.clear()

        for anime in animes:
            # (id, pattern, last_ep, res, last_dl, cover_url, official_title, status, has_new)
            iid = str(anime[0])
            self._anime_data[iid] = anime

            display_title  = anime[6] or anime[1]
            last_dl        = anime[4] or "—"
            status_raw     = anime[7] or ""
            status_pt      = STATUS_PT.get(status_raw, status_raw or "—")
            has_new        = bool(anime[8])

            tags = []
            if status_raw == "Currently Airing":  tags.append("airing")
            elif status_raw == "Finished Airing": tags.append("finished")
            elif status_raw == "Not yet aired":   tags.append("upcoming")
            if has_new: tags.append("new_ep")

            self.tree.insert("", tk.END, iid=iid, tags=tags, values=[
                str(anime[0]),
                ("🔥 " if has_new else "") + display_title,
                str(anime[2]),
                str(anime[3]),
                last_dl,
                status_pt,
            ])

    def _refresh_table(self):
        run_async(self._load_table_async(), on_done=self._on_table_loaded)

    # ─── Sidebar ──────────────────────────────────────────────────────────────

    def _on_row_select(self, event=None):
        selected = self.tree.selection()
        if not selected:
            return
        iid = selected[0]
        if iid == self._current_sidebar_iid:
            return
        self._current_sidebar_iid = iid
        data = self._anime_data.get(iid)
        if not data:
            return
        self._update_sidebar(iid, data)

    def _update_sidebar(self, iid: str, data: tuple):
        official_title = data[6] or data[1]
        status_raw     = data[7] or ""
        cover_url      = data[5]
        has_new        = bool(data[8])

        self.sidebar_title.config(text=official_title)

        status_pt    = STATUS_PT.get(status_raw, status_raw or "Desconhecido")
        status_color = STATUS_COLORS.get(status_raw, "#ffeb3b")
        self.sidebar_status.config(text=status_pt, fg=status_color)

        self.sidebar_new_badge.config(text="🔥 NOVO EPISÓDIO" if has_new else "")

        # Status da legenda (busca síncrona leve — só leitura de disco + ffprobe)
        self.sidebar_sub_status.config(text="verificando…", fg="#555555")
        self.after(50, lambda p=data[1], i=iid: self._refresh_sub_status(p, i))

        # Capa
        if iid in self._cover_cache:
            self.cover_label.configure(image=self._cover_cache[iid])
        elif cover_url:
            self._set_placeholder_cover()
            run_async(
                download_cover(cover_url, data[1]),
                on_done=lambda path, i=iid: self._on_cover_downloaded(path, i),
            )
        else:
            self._set_placeholder_cover()

    def _on_cover_downloaded(self, path, iid: str):
        if not path or isinstance(path, Exception):
            return
        try:
            img = Image.open(path).convert("RGB")
            img.thumbnail((COVER_W, COVER_H), Image.LANCZOS)
            # Pad to exact size
            canvas = Image.new("RGB", (COVER_W, COVER_H), "#333333")
            offset = ((COVER_W - img.width) // 2, (COVER_H - img.height) // 2)
            canvas.paste(img, offset)
            ref = ImageTk.PhotoImage(canvas)
            self._cover_cache[iid] = ref
            if self._current_sidebar_iid == iid:
                self.cover_label.configure(image=ref)
                self.cover_label.image = ref
        except Exception as e:
            print(f"Erro ao exibir capa: {e}")

    def _on_cover_click(self, event=None):
        """Abre a capa em tamanho ampliado numa janela popup."""
        if not self._current_sidebar_iid:
            return
        data = self._anime_data.get(self._current_sidebar_iid)
        if not data:
            return

        pattern = data[1]
        safe = re.sub(r'[^\w\s-]', '', pattern).strip().lower().replace(' ', '_')
        cover_path = os.path.join(COVERS_DIR, f"{safe}.jpg")
        if not os.path.exists(cover_path):
            return

        try:
            orig_img = Image.open(cover_path).convert("RGB")
        except Exception as e:
            print(f"Erro ao abrir capa ampliada: {e}")
            return

        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        init = orig_img.copy()
        init.thumbnail((int(sw * 0.75), int(sh * 0.85)), Image.LANCZOS)
        ref = ImageTk.PhotoImage(init)

        popup = tk.Toplevel(self)
        popup.title(data[6] or pattern)
        popup.configure(bg="#1e1e1e")
        popup.resizable(True, True)
        popup.minsize(150, 200)

        lbl = tk.Label(popup, image=ref, bg="#1e1e1e", cursor="hand2")
        lbl.image = ref
        lbl.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        lbl.bind("<Button-1>", lambda e: popup.destroy())
        popup.bind("<Escape>", lambda e: popup.destroy())

        # Redimensiona a imagem quando a janela é redimensionada
        resize_job = [None]
        last_size = [init.width, init.height]

        def _do_resize(w, h):
            if w < 50 or h < 50:
                return
            tmp = orig_img.copy()
            tmp.thumbnail((w - 8, h - 8), Image.LANCZOS)
            new_ref = ImageTk.PhotoImage(tmp)
            lbl.configure(image=new_ref)
            lbl.image = new_ref

        def _on_resize(event):
            if event.widget is not popup:
                return
            if event.width == last_size[0] and event.height == last_size[1]:
                return
            last_size[0], last_size[1] = event.width, event.height
            if resize_job[0]:
                popup.after_cancel(resize_job[0])
            resize_job[0] = popup.after(80, lambda w=event.width, h=event.height: _do_resize(w, h))

        popup.bind("<Configure>", _on_resize)

        pw = init.width + 8
        ph = init.height + 8
        sx = self.winfo_x() + (self.winfo_width() - pw) // 2
        sy = self.winfo_y() + (self.winfo_height() - ph) // 2
        popup.geometry(f"{pw}x{ph}+{sx}+{sy}")
        popup.transient(self)
        popup.update()
        popup.grab_set()

    # ─── Autocomplete ─────────────────────────────────────────────────────────

    def _on_entry_key(self, event):
        if event.keysym in ("Down", "Up"):
            if self._suggest_popup:
                self._suggest_popup.focus_set()
            return
        if event.keysym == "Escape":
            self._close_suggestions()
            return
        if self._suggest_after_id:
            self.after_cancel(self._suggest_after_id)
        query = self.entry.get().strip()
        if len(query) < 3 or ":" in query:
            self._close_suggestions()
            return
        self._suggest_after_id = self.after(420, lambda: self._fetch_suggestions(query))

    def _fetch_suggestions(self, query):
        def on_done(results):
            if isinstance(results, Exception) or not results:
                self._close_suggestions()
                return
            if not self.entry.get().strip().lower().startswith(query[:3].lower()):
                return
            self._show_suggestions(results)
        run_async(search_jikan(query), on_done=on_done)

    def _show_suggestions(self, titles):
        self._close_suggestions()
        self.update_idletasks()
        ex = self.entry.winfo_rootx()
        ey = self.entry.winfo_rooty() + self.entry.winfo_height()
        ew = self.entry.winfo_width()

        popup = tk.Toplevel(self)
        popup.wm_overrideredirect(True)
        popup.geometry(f"{ew}x{min(len(titles), 8) * 24}+{ex}+{ey}")
        popup.configure(bg="#2a2a2a")
        self._suggest_popup = popup

        lb = tk.Listbox(popup, bg="#2a2a2a", fg="#ffffff", selectbackground="#1565c0",
                        font=("Segoe UI", 10), bd=0, highlightthickness=1,
                        highlightcolor="#555", activestyle="none")
        lb.pack(fill=tk.BOTH, expand=True)
        for t in titles:
            lb.insert(tk.END, t)

        def select(event=None):
            sel = lb.curselection()
            if sel:
                self.entry.delete(0, tk.END)
                self.entry.insert(0, lb.get(sel[0]))
            self._close_suggestions()
            self.entry.focus_set()

        lb.bind("<ButtonRelease-1>", select)
        lb.bind("<Return>", select)
        lb.bind("<Escape>", lambda e: (self._close_suggestions(), self.entry.focus_set()))
        popup.bind("<FocusOut>", lambda e: self.after(150, self._close_suggestions))

    def _close_suggestions(self):
        if self._suggest_popup:
            try:
                self._suggest_popup.destroy()
            except Exception:
                pass
            self._suggest_popup = None

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
                self.notify("Anime Monitor", f"{len(result)} novo(s) episódio(s) iniciado(s)!")
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

    def _action_delete(self):
        selected = self.tree.selection()
        if not selected:
            self.log("Nenhum anime selecionado para remover.", "red")
            return
        iid = selected[0]
        data = self._anime_data.get(iid)
        if not data:
            return
        anime_id   = data[0]
        anime_name = data[6] or data[1]

        def on_done(_):
            self.log(f"Anime '{anime_name}' removido.", "orange")
            if self._current_sidebar_iid == iid:
                self._current_sidebar_iid = None
                self._set_placeholder_cover()
                self.sidebar_title.config(text="—")
                self.sidebar_status.config(text="")
                self.sidebar_new_badge.config(text="")
            self._refresh_table()

        run_async(remove_anime(anime_id), on_done=on_done)

    def _action_play(self):
        selected = self.tree.selection()
        if not selected:
            self.log("Selecione um anime para dar Play.", "red")
            return
        iid  = selected[0]
        data = self._anime_data.get(iid)
        if not data:
            return
        pattern = data[1].lower()

        if not os.path.exists(FINAL_DIR):
            self.log("Pasta de episódios não encontrada.", "red")
            return

        video_exts = (".mkv", ".mp4", ".avi")
        matches = [
            f for f in os.listdir(FINAL_DIR)
            if f.lower().endswith(video_exts) and pattern in f.lower()
        ]
        if not matches:
            self.log(f"Nenhum episódio encontrado para '{pattern}'.", "yellow")
            return

        def ep_key(name):
            m = re.search(r'S\d+E(\d+)', name, re.I) or re.search(r'[\s-]0?(\d+)[\s(]', name)
            return int(m.group(1)) if m else 0

        matches.sort(key=ep_key)
        latest = os.path.join(FINAL_DIR, matches[-1])
        self.log(f"Abrindo: {matches[-1]}", "green")
        open_path(latest)

    def _action_open_folder(self):
        os.makedirs(FINAL_DIR, exist_ok=True)
        open_path(FINAL_DIR)
        self.log(f"Pasta aberta: {FINAL_DIR}", "cyan")

    def _action_mark_watched(self):
        selected = self.tree.selection()
        if not selected:
            return
        iid  = selected[0]
        data = self._anime_data.get(iid)
        if not data:
            return
        anime_id = data[0]
        pattern  = data[1]

        video_exts = (".mkv", ".mp4", ".avi")
        if os.path.exists(FINAL_DIR):
            matches = [
                f for f in os.listdir(FINAL_DIR)
                if f.lower().endswith(video_exts) and pattern.lower() in f.lower()
            ]
        else:
            matches = []

        files_to_delete = []
        for video_file in matches:
            files_to_delete.append(os.path.join(FINAL_DIR, video_file))
            name_no_ext = os.path.splitext(video_file)[0]
            for f in os.listdir(FINAL_DIR):
                if f.startswith(name_no_ext) and f.lower().endswith((".ass", ".srt")):
                    files_to_delete.append(os.path.join(FINAL_DIR, f))

        video_count = len([f for f in files_to_delete if f.lower().endswith(video_exts)])

        if not files_to_delete:
            self.log(f"Nenhum arquivo encontrado para '{pattern}'. Flag limpa.", "yellow")
            run_async(clear_new_episode_flag(anime_id), on_done=lambda _: self._refresh_table())
            return

        # Diálogo de confirmação
        dialog = tk.Toplevel(self)
        dialog.title("Confirmar Limpeza")
        dialog.configure(bg="#1e1e1e")
        dialog.resizable(False, False)
        self._center_dialog(dialog, 360, 150)

        tk.Label(
            dialog,
            text=f"Deletar {video_count} episódio(s) de '{pattern}'?",
            bg="#1e1e1e", fg="#ffffff", font=("Segoe UI", 10), wraplength=330,
        ).pack(pady=(16, 4))
        tk.Label(
            dialog, text="Vídeos e legendas serão removidos permanentemente.",
            bg="#1e1e1e", fg="#888888", font=("Segoe UI", 9),
        ).pack()

        confirmed = {"ok": False}

        def confirm():
            confirmed["ok"] = True
            dialog.destroy()

        btn_frame = tk.Frame(dialog, bg="#1e1e1e")
        btn_frame.pack(pady=12)
        ttk.Button(btn_frame, text="Deletar", command=confirm).pack(side=tk.LEFT, padx=8)
        ttk.Button(btn_frame, text="Cancelar", command=dialog.destroy).pack(side=tk.LEFT, padx=8)
        dialog.bind("<Escape>", lambda e: dialog.destroy())
        dialog.wait_window()

        if not confirmed["ok"]:
            return

        deleted = 0
        for fpath in files_to_delete:
            try:
                os.remove(fpath)
                deleted += 1
                self.log(f"Deletado: {os.path.basename(fpath)}", "orange")
            except Exception as e:
                self.log(f"Erro ao deletar {os.path.basename(fpath)}: {e}", "red")

        self.log(f"Limpeza concluída: {deleted} arquivo(s) removido(s).", "cyan")
        run_async(clear_new_episode_flag(anime_id), on_done=lambda _: self._refresh_table())

    # ─── Editar episódio / Atualizar metadados ────────────────────────────────

    def _action_edit_episode(self):
        selected = self.tree.selection()
        if not selected:
            self.log("Selecione um anime para editar o episódio.", "red")
            return
        iid  = selected[0]
        data = self._anime_data.get(iid)
        if not data:
            return

        anime_id    = data[0]
        name        = data[6] or data[1]
        current_ep  = data[2]

        dialog = tk.Toplevel(self)
        dialog.title("Editar Episódio")
        dialog.configure(bg="#1e1e1e")
        dialog.resizable(False, False)
        self._center_dialog(dialog, 340, 150)

        tk.Label(dialog, text=name, bg="#1e1e1e", fg="#ffffff",
                 font=("Segoe UI", 10, "bold"), wraplength=310).pack(pady=(14, 4))
        tk.Label(dialog, text="Último episódio registrado:",
                 bg="#1e1e1e", fg="#aaaaaa", font=("Segoe UI", 9)).pack()

        spinbox = ttk.Spinbox(dialog, from_=0, to=99999, width=10, font=("Segoe UI", 11))
        spinbox.set(current_ep)
        spinbox.pack(pady=6)

        saved = {"ok": False, "ep": current_ep}

        def confirm():
            try:
                saved["ep"] = int(spinbox.get())
            except ValueError:
                saved["ep"] = current_ep
            saved["ok"] = True
            dialog.destroy()

        btn_frame = tk.Frame(dialog, bg="#1e1e1e")
        btn_frame.pack(pady=4)
        ttk.Button(btn_frame, text="Salvar",   command=confirm).pack(side=tk.LEFT, padx=8)
        ttk.Button(btn_frame, text="Cancelar", command=dialog.destroy).pack(side=tk.LEFT, padx=8)
        dialog.bind("<Return>", lambda e: confirm())
        dialog.bind("<Escape>", lambda e: dialog.destroy())
        dialog.wait_window()

        if not saved["ok"]:
            return
        new_ep = saved["ep"]

        def on_done(_):
            self.log(f"Episódio de '{name}' atualizado: {current_ep} → {new_ep}", "cyan")
            self._refresh_table()

        run_async(set_last_episode(anime_id, new_ep), on_done=on_done)

    def _action_refresh_selected_metadata(self):
        selected = self.tree.selection()
        if not selected:
            self.log("Selecione um anime para atualizar os metadados.", "red")
            return
        iid  = selected[0]
        data = self._anime_data.get(iid)
        if not data:
            return
        anime_id, pattern = data[0], data[1]
        name = data[6] or pattern
        self.log(f"Buscando metadados de '{name}'...", "blue")

        def on_done(result):
            if isinstance(result, Exception) or not result:
                self.log(f"Metadados não encontrados para '{name}'.", "yellow")
                return
            self.log(f"Metadados atualizados: {result.get('official_title', name)}", "cyan")
            # Invalida cache de capa para forçar re-download
            if iid in self._cover_cache:
                del self._cover_cache[iid]
            self._refresh_table()

        run_async(refresh_single_metadata(anime_id, pattern), on_done=on_done)

    def _action_refresh_all_metadata(self):
        self.log("Atualizando metadados de todos os animes…", "blue")

        def on_done(result):
            if isinstance(result, Exception):
                self.log(f"Erro ao atualizar metadados: {result}", "red")
                return
            count = len(result) if result else 0
            self.log(f"Metadados atualizados: {count} anime(s).", "cyan")
            # Limpa cache de capas para forçar re-download com imagens novas
            self._cover_cache.clear()
            self._current_sidebar_iid = None
            self._refresh_table()

        run_async(refresh_all_metadata(), on_done=on_done)

    # ─── Subtitle status (Item 10) ────────────────────────────────────────────

    def _refresh_sub_status(self, pattern: str, iid: str):
        """Encontra o último vídeo do anime e verifica o status da legenda."""
        if not os.path.exists(FINAL_DIR):
            return
        video_exts = (".mkv", ".mp4", ".avi")

        def ep_sort(name):
            m = re.search(r'S\d+E(\d+)', name, re.I) or re.search(r'[\s-]0?(\d+)[\s(]', name)
            return int(m.group(1)) if m else 0

        matches = sorted(
            [f for f in os.listdir(FINAL_DIR)
             if f.lower().endswith(video_exts) and pattern.lower() in f.lower()],
            key=ep_sort,
        )
        if not matches:
            if iid == self._current_sidebar_iid:
                self.sidebar_sub_status.config(text="Sem episódios locais", fg="#555555")
            return

        video_path = os.path.join(FINAL_DIR, matches[-1])
        status = check_subtitle_status(video_path)

        if status["embedded"] and status["external"]:
            langs = ", ".join(status["embedded_langs"])
            text, color = f"✓ Embutida ({langs}) + externa", "#4caf50"
        elif status["embedded"]:
            langs = ", ".join(status["embedded_langs"]) or "?"
            text, color = f"✓ Embutida ({langs})", "#4caf50"
        elif status["external"]:
            text, color = f"✓ {status['external']}", "#4caf50"
        else:
            text, color = "⚠ Sem legenda", "#ff9800"

        if iid == self._current_sidebar_iid:
            self.sidebar_sub_status.config(text=text, fg=color)

    # ─── Subtitle selector (Item 9) ───────────────────────────────────────────

    def _action_download_subs(self):
        self.log("Buscando legendas disponíveis...", "blue")

        def on_candidates(result):
            if isinstance(result, Exception):
                self.log(f"Erro ao buscar legendas: {result}", "red")
                return
            self._process_subtitle_candidates(result)

        run_async(get_subtitle_candidates(), on_done=on_candidates)

    def _process_subtitle_candidates(self, candidates):
        if not candidates:
            self.log("Nenhum anime com episódio registrado.", "yellow")
            return

        to_auto, to_select = [], []
        for c in candidates:
            if not c["subs"]:
                self.log(f"Legenda não encontrada: {c['pattern']} - Ep {c['last_ep']}", "yellow")
            elif len(c["subs"]) == 1:
                to_auto.append(c)
            else:
                to_select.append(c)

        for c in to_auto:
            run_async(
                download_chosen_subtitle(c["subs"][0], c["series_name"], c["ep_str"]),
                on_done=lambda path, p=c["pattern"], ep=c["ep_str"]: self._on_sub_downloaded(path, p, ep),
            )

        self._subtitle_selection_queue(to_select, 0)

    def _subtitle_selection_queue(self, queue, index):
        if index >= len(queue):
            if queue:
                self._run_organize_logic()
            return
        c = queue[index]
        chosen = self._show_subtitle_selector(c["pattern"], c["last_ep"], c["subs"])
        if chosen:
            run_async(
                download_chosen_subtitle(chosen, c["series_name"], c["ep_str"]),
                on_done=lambda path, p=c["pattern"], ep=c["ep_str"]: self._on_sub_downloaded(path, p, ep),
            )
        else:
            self.log(f"Legenda pulada: {c['pattern']} - Ep {c['last_ep']}", "yellow")
        self._subtitle_selection_queue(queue, index + 1)

    def _show_subtitle_selector(self, pattern, ep_num, subs):
        """Diálogo modal de seleção. Retorna o sub escolhido ou None."""
        dialog = tk.Toplevel(self)
        dialog.title(f"{pattern} — Ep {ep_num}")
        dialog.configure(bg="#1e1e1e")
        dialog.resizable(False, True)
        h = min(120 + len(subs) * 52, 520)
        self._center_dialog(dialog, 500, h)

        tk.Label(
            dialog,
            text=f"{len(subs)} legendas disponíveis para:\n{pattern} — Ep {ep_num}",
            bg="#1e1e1e", fg="#ffffff", font=("Segoe UI", 10, "bold"), justify=tk.CENTER,
        ).pack(pady=(14, 8))

        selected_var = tk.IntVar(value=0)
        sub_frame = tk.Frame(dialog, bg="#1e1e1e")
        sub_frame.pack(fill=tk.BOTH, expand=True, padx=14)

        lang_flags = {"por": "🇧🇷 PT", "eng": "🇬🇧 EN", "spa": "🇪🇸 ES"}

        for i, sub in enumerate(subs):
            info     = sub.get("info", {})
            lang     = info.get("lang", "unk")
            desc     = info.get("desc", "")
            filename = sub.get("filename", f"Legenda {i + 1}")
            lang_str = lang_flags.get(lang, lang.upper())

            row = tk.Frame(sub_frame, bg="#2a2a2a")
            row.pack(fill=tk.X, pady=2)

            tk.Radiobutton(
                row, variable=selected_var, value=i,
                bg="#2a2a2a", activebackground="#2a2a2a",
                selectcolor="#1565c0", fg="#ffffff",
            ).pack(side=tk.LEFT, padx=6)

            info_col = tk.Frame(row, bg="#2a2a2a")
            info_col.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=5)

            name_text = filename if len(filename) <= 58 else filename[:55] + "…"
            tk.Label(info_col, text=name_text, bg="#2a2a2a", fg="#ffffff",
                     font=("Segoe UI", 9), anchor=tk.W).pack(anchor=tk.W)
            detail = lang_str + (f"  •  {desc}" if desc else "")
            tk.Label(info_col, text=detail, bg="#2a2a2a", fg="#888888",
                     font=("Segoe UI", 8), anchor=tk.W).pack(anchor=tk.W)

        chosen = {"sub": None}

        def confirm():
            chosen["sub"] = subs[selected_var.get()]
            dialog.destroy()

        btn_frame = tk.Frame(dialog, bg="#1e1e1e")
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="Baixar Selecionada", command=confirm).pack(side=tk.LEFT, padx=8)
        ttk.Button(btn_frame, text="Pular", command=dialog.destroy).pack(side=tk.LEFT, padx=8)
        dialog.bind("<Escape>", lambda e: dialog.destroy())
        dialog.wait_window()
        return chosen["sub"]

    def _on_sub_downloaded(self, path, pattern, ep_str):
        if path and not isinstance(path, Exception):
            self.log(f"LEGENDA BAIXADA: {pattern} - Ep {int(ep_str)}", "green")
            # Atualiza status na sidebar se este anime estiver selecionado
            for iid, data in self._anime_data.items():
                if data[1] == pattern and iid == self._current_sidebar_iid:
                    self.after(100, lambda p=pattern, i=iid: self._refresh_sub_status(p, i))
        else:
            self.log(f"Falha ao baixar legenda: {pattern} - Ep {int(ep_str)}", "red")

    def _periodic_refresh(self):
        self._action_refresh()
        self.after(600_000, self._periodic_refresh)

    # ─── Context menu ─────────────────────────────────────────────────────────

    def _show_context_menu(self, event):
        row = self.tree.identify_row(event.y)
        if not row:
            return
        self.tree.selection_set(row)

        if hasattr(self, '_ctx_menu') and self._ctx_menu:
            try:
                self._ctx_menu.unpost()
            except Exception:
                pass
            self._ctx_menu = None

        menu = tk.Menu(self, tearoff=0, bg="#2a2a2a", fg="#ffffff",
                       activebackground="#1565c0", activeforeground="#ffffff",
                       font=("Segoe UI", 10))
        menu.add_command(label="▶ Play",                  command=self._action_play)
        menu.add_command(label="📁 Abrir Pasta",           command=self._action_open_folder)
        menu.add_separator()
        menu.add_command(label="✏ Editar Episódio",        command=self._action_edit_episode)
        menu.add_command(label="🔄 Atualizar Metadados",   command=self._action_refresh_selected_metadata)
        menu.add_command(label="🔍 Buscar Legenda",        command=self._action_force_sub_selected)
        menu.add_separator()
        menu.add_command(label="✓ Marcar como Visto",      command=self._action_mark_watched)
        menu.add_separator()
        menu.add_command(label="🗑 Remover da Lista",       command=self._action_delete)

        self._ctx_menu = menu
        menu.bind("<Unmap>", lambda e: setattr(self, '_ctx_menu', None))
        menu.tk_popup(event.x_root, event.y_root)

    def _action_force_sub_selected(self):
        selected = self.tree.selection()
        if not selected:
            self.log("Selecione um anime para buscar a legenda.", "red")
            return
        iid  = selected[0]
        data = self._anime_data.get(iid)
        if not data:
            return
        pattern, last_ep = data[1], data[2]
        if last_ep <= 0:
            self.log(f"Nenhum episódio registrado para '{pattern}'.", "yellow")
            return
        self.log(f"Buscando legenda: {pattern} - Ep {last_ep}...", "blue")

        def on_candidates(result):
            if isinstance(result, Exception):
                self.log(f"Erro ao buscar legenda: {result}", "red")
                return
            subs, series_name, ep_str = result
            if not subs:
                self.log(f"Legenda não encontrada: {pattern} - Ep {last_ep}", "yellow")
                return
            if len(subs) == 1:
                run_async(
                    download_chosen_subtitle(subs[0], series_name, ep_str),
                    on_done=lambda path: self._on_sub_downloaded(path, pattern, ep_str),
                )
            else:
                chosen = self._show_subtitle_selector(pattern, last_ep, subs)
                if chosen:
                    run_async(
                        download_chosen_subtitle(chosen, series_name, ep_str),
                        on_done=lambda path: self._on_sub_downloaded(path, pattern, ep_str),
                    )
                else:
                    self.log(f"Legenda pulada: {pattern} - Ep {last_ep}", "yellow")

        run_async(find_subtitles(pattern, last_ep), on_done=on_candidates)

    # ─── Add Anime ────────────────────────────────────────────────────────────

    def _add_anime(self):
        raw = self.entry.get().strip()

        if not raw:
            self.log("Digite o nome do anime antes de adicionar.", "red")
            return

        if ":" in raw:
            parts = raw.rsplit(":", 1)
            name = parts[0].strip()
            try:
                start_ep = int(parts[1].strip())
            except ValueError:
                start_ep = 0
            self._confirm_add(name, start_ep, history=None)
            return

        name = raw
        self.log(f"Buscando histórico de '{name}'...", "blue")

        def on_history(result):
            if isinstance(result, Exception):
                self.log(f"Erro ao buscar histórico: {result}", "red")
                history, max_ep = None, 0
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
        self._center_dialog(dialog, 340, 160)

        msg = f"{max_ep} episódios encontrados." if max_ep > 0 else "Nenhum episódio encontrado no histórico."
        tk.Label(dialog, text=msg, bg="#1e1e1e", fg="#ffffff", font=("Segoe UI", 10)).pack(pady=(16, 4))
        tk.Label(dialog, text="A partir de qual episódio deseja baixar?",
                 bg="#1e1e1e", fg="#aaaaaa", font=("Segoe UI", 9)).pack()

        initial = max(0, max_ep - 2) if max_ep > 0 else 0
        spinbox = ttk.Spinbox(dialog, from_=0, to=max(max_ep, 9999), width=10, font=("Segoe UI", 11))
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

        ttk.Button(btn_frame, text="Confirmar", command=confirm).pack(side=tk.LEFT, padx=8)
        ttk.Button(btn_frame, text="Cancelar", command=dialog.destroy).pack(side=tk.LEFT, padx=8)
        dialog.bind("<Return>", lambda e: confirm())
        dialog.bind("<Escape>", lambda e: dialog.destroy())
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

            # Busca metadados em background (capa, título oficial, status)
            self._fetch_metadata_for(name)

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
                        self.log("Nenhum episódio novo no histórico.", "yellow")
                run_async(process_releases(history), on_done=on_releases)
            else:
                self.log("Histórico não encontrado. Verificando feed geral...", "yellow")
                self._action_refresh()

        run_async(add_anime(name, start_episode=start_ep), on_done=on_added)

    def _fetch_metadata_for(self, title_pattern: str):
        """Busca metadados Jikan e salva no banco para o anime de dado padrão."""
        async def _task():
            animes = await get_monitored_animes()
            row = next((a for a in animes if a[1] == title_pattern), None)
            if not row:
                return
            meta = await fetch_anime_metadata(title_pattern)
            if not meta:
                return
            await update_anime_metadata(
                row[0], meta["official_title"], meta["cover_url"], meta["airing_status"]
            )
            return await get_monitored_animes()

        def on_done(result):
            if isinstance(result, Exception) or not result:
                return
            self._on_table_loaded(result)

        run_async(_task(), on_done=on_done)


if __name__ == "__main__":
    app = AnimeMonitorApp()
    app.mainloop()
