import asyncio
import os
import re
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk, ImageDraw
from ...core.config import STATUS_COLORS, STATUS_PT, COVER_W, COVER_H, COVERS_DIR, VERSION
from ...core.downloader import download_cover, check_subtitle_status, open_path, matches_pattern, get_final_dir
from ...utils.async_bridge import run_async
from ...utils.episode_parser import extract_episode_number

class AnimeSidebar(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg="#252525", width=170, **kwargs)
        self.pack_propagate(False)
        self._cover_cache = {}
        self._current_iid = None
        self._current_pattern = None

        self._build_ui()

    def _build_ui(self):
        self.cover_label = tk.Label(self, bg="#252525", cursor="hand2")
        self.cover_label.pack(pady=(12, 6))
        self.cover_label.bind("<Button-1>", self._on_cover_click)
        self._set_placeholder_cover()

        self.sidebar_title = tk.Label(
            self, text="—", bg="#252525", fg="#ffffff",
            font=("Segoe UI", 9, "bold"), wraplength=155, justify=tk.CENTER,
        )
        self.sidebar_title.pack(padx=6, pady=(0, 4))

        self.sidebar_status = tk.Label(
            self, text="", bg="#252525", fg="#888888",
            font=("Segoe UI", 9), wraplength=155, justify=tk.CENTER,
        )
        self.sidebar_status.pack(padx=6)

        self.sidebar_new_badge = tk.Label(
            self, text="", bg="#252525", fg="#ff9800",
            font=("Segoe UI", 9, "bold"),
        )
        self.sidebar_new_badge.pack(pady=(4, 0))

        ttk.Separator(self, orient="horizontal").pack(fill=tk.X, padx=8, pady=(10, 4))
        tk.Label(self, text="Legenda", bg="#252525", fg="#555555",
                 font=("Segoe UI", 8)).pack()
        
        self.sidebar_sub_status = tk.Label(
            self, text="", bg="#252525", fg="#555555",
            font=("Segoe UI", 8), wraplength=155, justify=tk.CENTER,
        )
        self.sidebar_sub_status.pack(padx=6, pady=(10, 0))

        # Spacer
        tk.Frame(self, bg="#252525").pack(expand=True, fill=tk.BOTH)

        version_label = tk.Label(
            self, text=f"Versão: {VERSION}", bg="#252525", fg="#666666",
            font=("Segoe UI", 7)
        )
        version_label.pack(pady=(0, 5))

    def _set_placeholder_cover(self):
        img = Image.new("RGB", (COVER_W, COVER_H), "#333333")
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, COVER_W - 1, COVER_H - 1], outline="#555555", width=2)
        ref = ImageTk.PhotoImage(img)
        self.cover_label.configure(image=ref)
        self.cover_label.image = ref

    def update_info(self, iid, data):
        self._current_iid = iid
        self._current_pattern = data[1]
        official_title = data[6] or data[1]
        status_raw     = data[7] or ""
        cover_url      = data[5]
        has_new        = bool(data[8])

        self.sidebar_title.config(text=official_title)
        status_pt    = STATUS_PT.get(status_raw, status_raw or "Desconhecido")
        status_color = STATUS_COLORS.get(status_raw, "#ffeb3b")
        self.sidebar_status.config(text=status_pt, fg=status_color)
        self.sidebar_new_badge.config(text="🔥 NOVO EPISÓDIO" if has_new else "")

        self.sidebar_sub_status.config(text="verificando…", fg="#555555")
        self.refresh_sub_status(data[1])

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

    def _on_cover_downloaded(self, path, iid):
        if not path or isinstance(path, Exception): return
        try:
            img = Image.open(path).convert("RGB")
            img.thumbnail((COVER_W, COVER_H), Image.LANCZOS)
            canvas = Image.new("RGB", (COVER_W, COVER_H), "#333333")
            offset = ((COVER_W - img.width) // 2, (COVER_H - img.height) // 2)
            canvas.paste(img, offset)
            ref = ImageTk.PhotoImage(canvas)
            self._cover_cache[iid] = ref
            if self._current_iid == iid:
                self.cover_label.configure(image=ref)
                self.cover_label.image = ref
        except Exception as e:
            print(f"Erro ao exibir capa: {e}")

    def refresh_sub_status(self, pattern):
        final_dir = get_final_dir()
        video_exts = (".mkv", ".mp4", ".avi")

        def _scan_and_check():
            if not os.path.exists(final_dir):
                return None
            files = [
                f for f in os.listdir(final_dir)
                if f.lower().endswith(video_exts) and matches_pattern(f, pattern)
            ]
            if not files:
                return None
            latest = sorted(files, key=lambda n: extract_episode_number(n) or 0)[-1]
            return check_subtitle_status(os.path.join(final_dir, latest))

        def on_done(result):
            if self._current_pattern != pattern:
                return
            if result is None or isinstance(result, Exception):
                self.sidebar_sub_status.config(text="Sem episódios locais", fg="#555555")
                return
            if result["embedded"] and result["external"]:
                langs = ", ".join(result["embedded_langs"])
                text, color = f"✓ Embutida ({langs}) + externa", "#4caf50"
            elif result["embedded"]:
                langs = ", ".join(result["embedded_langs"]) or "?"
                text, color = f"✓ Embutida ({langs})", "#4caf50"
            elif result["external"]:
                text, color = f"✓ {result['external']}", "#4caf50"
            else:
                text, color = "⚠ Sem legenda", "#ff9800"
            self.sidebar_sub_status.config(text=text, fg=color)

        run_async(asyncio.to_thread(_scan_and_check), on_done=on_done)

    def _on_cover_click(self, event=None):
        if not self._current_pattern: return
        safe = re.sub(r'[^\w\s-]', '', self._current_pattern).strip().lower().replace(' ', '_')
        cover_path = os.path.join(COVERS_DIR, f"{safe}.jpg")
        if not os.path.exists(cover_path): return

        try:
            orig_img = Image.open(cover_path).convert("RGB")
        except Exception: return

        # Obter a root window para centralizar
        root = self.winfo_toplevel()
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        
        init = orig_img.copy()
        init.thumbnail((int(sw * 0.75), int(sh * 0.85)), Image.LANCZOS)
        ref = ImageTk.PhotoImage(init)

        popup = tk.Toplevel(self)
        popup.title(self._current_pattern)
        popup.configure(bg="#1e1e1e")
        popup.resizable(True, True)

        lbl = tk.Label(popup, image=ref, bg="#1e1e1e", cursor="hand2")
        lbl.image = ref
        lbl.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        lbl.bind("<Button-1>", lambda e: popup.destroy())
        popup.bind("<Escape>", lambda e: popup.destroy())

        def _do_resize(w, h):
            if w < 50 or h < 50: return
            tmp = orig_img.copy()
            tmp.thumbnail((w - 8, h - 8), Image.LANCZOS)
            new_ref = ImageTk.PhotoImage(tmp)
            lbl.configure(image=new_ref)
            lbl.image = new_ref

        last_size = [init.width, init.height]
        resize_job = [None]

        def _on_resize(event):
            if event.widget is not popup: return
            if event.width == last_size[0] and event.height == last_size[1]: return
            last_size[0], last_size[1] = event.width, event.height
            if resize_job[0]: popup.after_cancel(resize_job[0])
            resize_job[0] = popup.after(80, lambda w=event.width, h=event.height: _do_resize(w, h))

        popup.bind("<Configure>", _on_resize)
        pw, ph = init.width + 8, init.height + 8
        popup.geometry(f"{pw}x{ph}")
        popup.transient(root)
        popup.grab_set()

    def clear(self):
        self._current_iid = None
        self._current_pattern = None
        self._set_placeholder_cover()
        self.sidebar_title.config(text="—")
        self.sidebar_status.config(text="")
        self.sidebar_new_badge.config(text="")
        self.sidebar_sub_status.config(text="")

    def clear_cache(self):
        self._cover_cache.clear()
