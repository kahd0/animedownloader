import tkinter as tk
from tkinter import ttk
import re
from ...core.downloader import download_chosen_subtitle
from ...utils.async_bridge import run_async

class SubtitleSelectorDialog(tk.Toplevel):
    def __init__(self, parent, pattern, ep_num, subs, series_name, ep_str, log_callback, on_done_callback):
        super().__init__(parent)
        self.parent = parent
        self.pattern = pattern
        self.ep_num = ep_num
        self.subs = subs
        self.series_name = series_name
        self.ep_str = ep_str
        self.log_callback = log_callback
        self.on_done_callback = on_done_callback
        
        self.chosen_sub = None

        self.title(f"{pattern} — Ep {ep_num}")
        self.configure(bg="#1e1e1e")
        self._center_dialog(520, 460)
        self.transient(parent)
        self.grab_set()

        self._build_ui()

    def _center_dialog(self, width, height):
        self.update_idletasks()
        x = self.parent.winfo_x() + (self.parent.winfo_width() // 2) - (width // 2)
        y = self.parent.winfo_y() + (self.parent.winfo_height() // 2) - (height // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _build_ui(self):
        tk.Label(self, text=f"{len(self.subs)} legendas disponíveis para:\n{self.pattern} — Ep {self.ep_num}",
                 bg="#1e1e1e", fg="#ffffff", font=("Segoe UI", 10, "bold"), justify=tk.CENTER
                 ).pack(pady=(14, 8))

        btn_frame = tk.Frame(self, bg="#1e1e1e")
        btn_frame.pack(side=tk.BOTTOM, pady=10)
        
        ttk.Button(btn_frame, text="Baixar Selecionada", command=self._confirm).pack(side=tk.LEFT, padx=8)
        ttk.Button(btn_frame, text="Pular", command=self.destroy).pack(side=tk.LEFT, padx=8)

        container = tk.Frame(self, bg="#1e1e1e")
        container.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 4))

        canvas = tk.Canvas(container, bg="#1e1e1e", highlightthickness=0)
        vsb = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg="#1e1e1e")

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=vsb.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self.selected_var = tk.IntVar(value=0)
        
        for i, s in enumerate(self.subs):
            row_bg = "#1e1e1e" if i % 2 == 0 else "#121212"
            row = tk.Frame(scrollable_frame, bg=row_bg, pady=4)
            row.pack(fill=tk.X)
            
            rb = tk.Radiobutton(row, variable=self.selected_var, value=i, bg=row_bg, 
                               activebackground=row_bg, selectcolor="#1565c0", highlightthickness=0)
            rb.pack(side=tk.LEFT, padx=4)

            info_col = tk.Frame(row, bg=row_bg)
            info_col.pack(side=tk.LEFT, fill=tk.X, expand=True)

            info = s.get('info', {})
            lang = info.get('lang', 'und')
            desc = info.get('desc', '')
            is_br = (lang == 'por' and 'forced' not in desc.lower() and 'cc' not in desc.lower())
            
            lang_str = "Português (Brasil)" if lang == 'por' else "Inglês" if lang == 'eng' else lang.upper()
            fg_main = "#4caf50" if is_br else "#ffffff"
            fg_detail = "#888888"

            name_text = s.get('filename') or f"[{lang_str}] Legenda #{i+1}"
            tk.Label(info_col, text=name_text, bg=row_bg, fg=fg_main,
                     font=("Segoe UI", 9), anchor=tk.W).pack(anchor=tk.W)

            source_badge = " [OpenSubtitles]" if s.get('source') == 'opensubtitles' else ""
            detail = ("★ " if is_br else "") + (f"{lang_str}  •  {desc}" if desc else lang_str) + source_badge
            tk.Label(info_col, text=detail, bg=row_bg, fg=fg_detail,
                     font=("Segoe UI", 8), anchor=tk.W).pack(anchor=tk.W)

    def _confirm(self):
        self.chosen_sub = self.subs[self.selected_var.get()]
        if self.on_done_callback:
            self.on_done_callback(self.chosen_sub)
        self.destroy()

class SubtitleQueueProcessor:
    def __init__(self, parent, queue, log_callback, on_sub_downloaded_callback, on_finished_callback):
        self.parent = parent
        self.queue = queue
        self.log_callback = log_callback
        self.on_sub_downloaded_callback = on_sub_downloaded_callback
        self.on_finished_callback = on_finished_callback
        self.index = 0

    def process_next(self):
        if self.index >= len(self.queue):
            if self.on_finished_callback:
                self.on_finished_callback()
            return

        c = self.queue[self.index]
        
        def on_chosen(chosen):
            if chosen:
                run_async(
                    download_chosen_subtitle(chosen, c["series_name"], c["ep_str"], target_video_path=c.get("video_path")),
                    on_done=lambda path, p=c["pattern"], ep=c["ep_str"]: self.on_sub_downloaded_callback(path, p, ep)
                )
            else:
                if self.log_callback:
                    self.log_callback(f"Legenda pulada: {c['pattern']} - Ep {c['last_ep']}", "yellow")
            
            self.index += 1
            # Delay pequeno para não abrir a próxima janela instantaneamente
            self.parent.after(100, self.process_next)

        SubtitleSelectorDialog(
            self.parent, 
            c["pattern"], 
            c["last_ep"], 
            c["subs"], 
            c["series_name"], 
            c["ep_str"], 
            self.log_callback,
            on_chosen
        )
