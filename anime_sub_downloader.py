import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import requests
import lzma
import os
import threading
import queue
import re

class SubtitleDialog(tk.Toplevel):
    def __init__(self, parent, subtitles):
        super().__init__(parent)
        self.title("Selecionar Legenda")
        self.geometry("950x600")
        self.result = None
        self.subtitles = subtitles

        tk.Label(self, text="Legendas encontradas para este episódio:", font=("Arial", 12, "bold")).pack(pady=10)
        tk.Label(self, text="Dica: Procure por 'Brazilian' ou 'Multi-Subs' (marcadas em azul).", fg="#555").pack()

        columns = ("Lang", "Desc", "Codec", "Source")
        self.tree = ttk.Treeview(self, columns=columns, show="headings")
        self.tree.heading("Lang", text="Idioma")
        self.tree.heading("Desc", text="Versão/Descrição")
        self.tree.heading("Codec", text="Formato")
        self.tree.heading("Source", text="Release (Torrent)")
        
        self.tree.column("Lang", width=120, anchor="center")
        self.tree.column("Desc", width=250, anchor="w")
        self.tree.column("Codec", width=80, anchor="center")
        self.tree.column("Source", width=480)
        
        self.tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        for i, sub in enumerate(subtitles):
            info = sub['attach'].get('info', {})
            lang_code = info.get('lang', 'unk')
            desc = info.get('desc', 'Subtitle')
            codec = info.get('codec', 'ass')
            source = sub['torrent_title']
            
            tags = ()
            lang_display = lang_code
            if lang_code == 'por':
                lang_display = "PORTUGUÊS (BR)"
                tags = ('highlight_main',) if "forced" not in desc.lower() and "cc" not in desc.lower() else ('highlight',)
            elif lang_code == 'eng':
                lang_display = "Inglês"
            
            self.tree.insert("", tk.END, iid=i, values=(lang_display, desc, codec, source), tags=tags)

        self.tree.tag_configure('highlight', background='#e3f2fd')
        self.tree.tag_configure('highlight_main', background='#90caf9', font=("Arial", 9, "bold"))
        
        self.tree.bind("<Double-1>", lambda e: self.on_select())
        tk.Button(self, text="BAIXAR SELECIONADA", command=self.on_select, 
                  bg="#1976D2", fg="white", font=("Arial", 11, "bold"), padx=40, pady=12).pack(pady=20)

        self.transient(parent)
        self.grab_set()
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (self.winfo_width() // 2)
        y = (self.winfo_screenheight() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")

    def on_select(self):
        selected = self.tree.selection()
        if selected:
            self.result = int(selected[0])
            self.destroy()
        else:
            messagebox.showwarning("Aviso", "Selecione uma legenda na lista.")

class AnimeSubApp:
    def __init__(self, root):
        self.root = root
        self.root.title("AnimeTosho Sub Downloader Pro")
        self.root.geometry("550x420")
        
        self.selected_file = ""
        self.result_queue = queue.Queue()

        tk.Label(root, text="Buscador de Legendas PT-BR", font=("Arial", 12, "bold")).pack(pady=15)
        tk.Button(root, text="1. Selecionar Episódio", command=self.browse_file, width=25).pack(pady=5)
        self.label_file = tk.Label(root, text="Nenhum arquivo selecionado", fg="gray", wraplength=500)
        self.label_file.pack(pady=10)

        self.btn_download = tk.Button(root, text="2. BUSCAR LEGENDAS", 
                                      command=self.start_download_thread, 
                                      state=tk.DISABLED, bg="#4CAF50", fg="white", 
                                      font=("Arial", 10, "bold"), padx=20, pady=10)
        self.btn_download.pack(pady=20)

        self.status_label = tk.Label(root, text="", font=("Arial", 9), wraplength=500)
        self.status_label.pack()

    def browse_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("Vídeos", "*.mkv *.mp4"), ("Todos", "*.*")])
        if file_path:
            self.selected_file = file_path
            self.label_file.config(text=os.path.basename(file_path), fg="black")
            self.btn_download.config(state=tk.NORMAL)

    def update_status(self, text, color="black"):
        self.status_label.config(text=text, fg=color)

    def start_download_thread(self):
        self.btn_download.config(state=tk.DISABLED)
        threading.Thread(target=self.download_subtitles, daemon=True).start()

    def get_episode_num(self, filename):
        # Tenta pegar o número do episódio de várias formas (01, E01, - 01)
        match = re.search(r'(?:[eE]|-\s*|\s+|^)(0?\d+)(?:\D|$)', filename)
        if match:
            return match.group(1).zfill(2)
        return ""

    def download_subtitles(self):
        file_path = self.selected_file
        file_base = os.path.basename(file_path)
        directory = os.path.dirname(file_path)
        
        # Limpa o nome para pegar só a série
        clean_name = re.sub(r'\[.*?\]|\(.*?\)', '', file_base)
        clean_name = os.path.splitext(clean_name)[0].strip()
        
        # Pega o número do episódio
        ep_num = self.get_episode_num(clean_name)
        
        # Tenta simplificar o nome da série para a busca
        series_name = re.sub(rf's\d+|e\d+|-.*$|\d+p.*$', '', clean_name, flags=re.I).strip()
        
        self.update_status(f"Buscando: {series_name} | Ep: {ep_num}", "blue")

        all_subs = []
        seen_attach_ids = set()

        # Queries: Nome da série + ep + termos chave
        queries = [
            f'{series_name} {ep_num}',
            f'{series_name} Multi',
            f'{series_name} Brazilian'
        ]
        
        for q in queries:
            try:
                # Busca sem aspas para ser mais flexível no AnimeTosho
                resp = requests.get("https://feed.animetosho.org/json", params={"q": q}, timeout=10)
                results = resp.json()
                
                for entry in results[:15]:
                    t_title = entry['title'].lower()
                    
                    # Se temos o ep_num, verificamos se ele aparece no título (ex: 01, E01, E1)
                    if ep_num:
                        ep_val = int(ep_num)
                        if not re.search(rf'([eE]|\s|-)0?{ep_val}(\D|$)', t_title):
                            continue

                    detail_resp = requests.get("https://feed.animetosho.org/json", params={"show": "torrent", "id": entry['id']}, timeout=10)
                    details = detail_resp.json()

                    for f in details.get('files', []):
                        f_name = f['filename'].lower()
                        # Verifica se o arquivo dentro do torrent bate com o episódio
                        is_match = False
                        if ep_num:
                            ep_val = int(ep_num)
                            if re.search(rf'([eE]|\s|-)0?{ep_val}(\D|$)', f_name):
                                is_match = True
                        
                        if is_match or not ep_num:
                            for a in f.get('attachments', []):
                                if a.get('type') == 'subtitle' and a['id'] not in seen_attach_ids:
                                    all_subs.append({'attach': a, 'torrent_title': entry['title']})
                                    seen_attach_ids.add(a['id'])
            except: continue

        if not all_subs:
            self.update_status("Nada encontrado. Tente buscar por um nome mais curto.", "red")
            self.btn_download.config(state=tk.NORMAL)
            return

        # Ordenação PT-BR
        def sort_key(s):
            info = s['attach'].get('info', {})
            lang = info.get('lang', 'unk')
            desc = info.get('desc', '').lower()
            if lang == 'por':
                if "forced" not in desc and "cc" not in desc: return 0
                return 1
            if lang == 'eng': return 2
            return 3
        
        all_subs.sort(key=sort_key)

        self.root.after(0, lambda: self.result_queue.put(self.show_selection_dialog(all_subs)))
        selected_index = self.result_queue.get()
        
        if selected_index is not None:
            sel = all_subs[selected_index]
            self.update_status("Baixando legenda...", "blue")
            try:
                dl_url = f"https://storage.animetosho.org/attach/{sel['attach']['id']:08x}/file.xz"
                data = lzma.decompress(requests.get(dl_url, timeout=15).content)
                ext = sel['attach']['info'].get('codec', 'ass').lower()
                final_path = os.path.join(directory, f"{os.path.splitext(file_base)[0]}.{ext}")
                with open(final_path, 'wb') as f: f.write(data)
                self.update_status("Sucesso!", "green")
                messagebox.showinfo("Sucesso", "Legenda baixada!")
            except Exception as e:
                self.update_status(f"Erro: {e}", "red")
        else:
            self.update_status("Busca cancelada.", "orange")
        
        self.btn_download.config(state=tk.NORMAL)

    def show_selection_dialog(self, subs):
        dialog = SubtitleDialog(self.root, subs)
        self.root.wait_window(dialog)
        return dialog.result

if __name__ == "__main__":
    root = tk.Tk()
    app = AnimeSubApp(root)
    root.mainloop()
