import httpx
import re
import webbrowser
import platform
import subprocess
import os
import lzma
import shutil
from database import get_monitored_animes, update_last_episode

API_URL = "https://subsplease.org/api/?f=latest&tz=UTC"
SEARCH_URL = "https://subsplease.org/api/?f=search&tz=UTC&s="
ANIMETOSHO_API = "https://feed.animetosho.org/json"

# Caminhos Base
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "Torrents")
FINAL_DIR = os.path.join(BASE_DIR, "episodes")
SUBS_TEMP_DIR = os.path.join(BASE_DIR, "legendas")

async def fetch_latest_releases():
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(API_URL, timeout=15)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching from SubsPlease: {e}")
            return {}

async def search_anime_history(query):
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{SEARCH_URL}{query}", timeout=15)
            response.raise_for_status()
            data = response.json()
            return data.items() if isinstance(data, dict) else []
        except Exception as e:
            print(f"Error searching anime history: {e}")
            return []

async def download_subtitle(show_name, ep_num):
    """Busca e baixa a melhor legenda PT-BR no AnimeTosho"""
    series_name = re.sub(rf's\d+|e\d+|-.*$|\d+p.*$', '', show_name, flags=re.I).strip()
    ep_str = str(ep_num).zfill(2)
    
    queries = [f'{series_name} {ep_str}', f'{series_name} Brazilian', f'{series_name} Multi']
    all_subs = []
    seen_ids = set()
    
    async with httpx.AsyncClient() as client:
        for q in queries:
            try:
                resp = await client.get(ANIMETOSHO_API, params={"q": q}, timeout=10)
                results = resp.json()
                for entry in results[:10]:
                    if not re.search(rf'(\s|-)0?{int(ep_num)}(\D|$)', entry['title']):
                        continue
                    det_resp = await client.get(ANIMETOSHO_API, params={"show": "torrent", "id": entry['id']})
                    details = det_resp.json()
                    for f in details.get('files', []):
                        if not re.search(rf'(\s|-)0?{int(ep_num)}(\D|$)', f['filename']):
                            continue
                        for a in f.get('attachments', []):
                            if a.get('type') == 'subtitle' and a['id'] not in seen_ids:
                                all_subs.append(a)
                                seen_ids.add(a['id'])
            except Exception as e:
                print(f"Erro busca legenda: {e}")
                continue

    if not all_subs: return None

    def sort_key(s):
        info = s.get('info', {})
        lang = info.get('lang', 'unk')
        desc = info.get('desc', '').lower()
        if lang == 'por':
            return 0 if "forced" not in desc and "cc" not in desc else 1
        return 2 if lang == 'eng' else 3
    
    all_subs.sort(key=sort_key)
    best_sub = all_subs[0]
    
    try:
        dl_url = f"https://storage.animetosho.org/attach/{best_sub['id']:08x}/file.xz"
        async with httpx.AsyncClient() as client:
            resp = await client.get(dl_url, timeout=15)
            resp.raise_for_status()
            data = lzma.decompress(resp.content)
            
        ext = best_sub['info'].get('codec', 'ass').lower()
        os.makedirs(SUBS_TEMP_DIR, exist_ok=True)
        # Limpa o nome do padrão para o arquivo temporário
        safe_pattern = re.sub(r'[^\w\s-]', '', series_name).strip().lower()
        filename = os.path.join(SUBS_TEMP_DIR, f"{safe_pattern}_ep{ep_str}.{ext}")
        with open(filename, 'wb') as f: f.write(data)
        return filename
    except Exception as e:
        print(f"Erro download/salvar legenda: {e}")
        return None

def trigger_magnet(magnet_link):
    try:
        if platform.system() == "Windows": os.startfile(magnet_link)
        elif platform.system() == "Darwin": subprocess.run(["open", magnet_link])
        else: subprocess.run(["xdg-open", magnet_link])
        return True
    except Exception as e:
        print(f"Erro ao abrir magnet: {e}")
        return webbrowser.open(magnet_link)

async def organize_downloads():
    """Move vídeos e busca legendas correspondentes"""
    os.makedirs(FINAL_DIR, exist_ok=True)
    moved_files = []

    # 1. Mover vídeos da pasta de Downloads para a pasta FINAL
    if os.path.exists(SOURCE_DIR):
        monitored = await get_monitored_animes()
        for filename in os.listdir(SOURCE_DIR):
            if filename.endswith((".!qB", ".part")): continue
            if not filename.lower().endswith((".mkv", ".mp4", ".avi")): continue

            for _, pattern, _, _ in monitored:
                if pattern.lower() in filename.lower():
                    old_path = os.path.join(SOURCE_DIR, filename)
                    new_path = os.path.join(FINAL_DIR, filename)
                    try:
                        shutil.move(old_path, new_path)
                        moved_files.append(f"Vídeo: {filename}")
                    except Exception as e: print(f"Erro ao mover vídeo {filename}: {e}")

    # 2. Parear legendas com vídeos na pasta FINAL
    # Varre a pasta de episódios final em busca de vídeos que precisem de legenda
    if os.path.exists(SUBS_TEMP_DIR):
        for video_file in os.listdir(FINAL_DIR):
            if not video_file.lower().endswith((".mkv", ".mp4", ".avi")): continue
            
            # Extrai o nome base e o episódio do vídeo
            # Ex: [SubsPlease] Show Name - 03 (1080p).mkv
            ep_match = re.search(rf'(\s|-)0?(\d+)(\D|$)', video_file)
            if not ep_match: continue
            
            ep_num = ep_match.group(2).zfill(2)
            video_name_no_ext = os.path.splitext(video_file)[0]
            
            # Verifica se já existe uma legenda para este vídeo na pasta final
            has_sub = any(video_name_no_ext in f and f.lower().endswith((".ass", ".srt")) for f in os.listdir(FINAL_DIR))
            if has_sub: continue

            # Tenta encontrar a legenda na pasta temporária
            for sub_file in os.listdir(SUBS_TEMP_DIR):
                # A legenda temporária tem o formato: "nome_do_anime_epXX.ass"
                # Verificamos se o ep bate e se o nome do anime está contido
                if f"_ep{ep_num}" in sub_file.lower():
                    # Sucesso! Move e renomeia
                    sub_ext = os.path.splitext(sub_file)[1]
                    old_sub_path = os.path.join(SUBS_TEMP_DIR, sub_file)
                    new_sub_path = os.path.join(FINAL_DIR, f"{video_name_no_ext}{sub_ext}")
                    try:
                        shutil.move(old_sub_path, new_sub_path)
                        moved_files.append(f"Legenda pareada: {video_file}")
                    except Exception as e: print(f"Erro ao mover legenda {sub_file}: {e}")
                    break
                    
    return moved_files

async def process_releases(releases_list, monitored_list=None):
    if monitored_list is None: monitored_list = await get_monitored_animes()
    if not monitored_list: return []
    downloads_triggered = []
    
    normalized = []
    for item in releases_list:
        normalized.append(item[1] if isinstance(item, tuple) else item)

    normalized.sort(key=lambda x: int(x.get('episode', 0)) if str(x.get('episode', '')).isdigit() else 0)

    for info in normalized:
        show_name = info.get('show', '')
        try: episode_num = int(info.get('episode', 0))
        except (ValueError, TypeError):
            continue

        for anime_id, pattern, last_ep, res in monitored_list:
            if pattern.lower() in show_name.lower() and episode_num > last_ep:
                magnet = None
                for dl in info.get('downloads', []):
                    if dl.get('res') == res.replace('p', ''):
                        magnet = dl.get('magnet'); break
                
                if not magnet and info.get('downloads'): magnet = info['downloads'][0].get('magnet')

                if magnet and trigger_magnet(magnet):
                    await update_last_episode(pattern, episode_num)
                    # Baixa a legenda para a pasta temporária
                    sub_file = await download_subtitle(show_name, episode_num)
                    sub_msg = " (Legenda baixada)" if sub_file else " (Legenda não encontrada ainda)"
                    downloads_triggered.append(f"{show_name} - {episode_num} ({res}){sub_msg}")
                    monitored_list = [(aid, p, episode_num if p == pattern else lep, r) for aid, p, lep, r in monitored_list]
    
    return downloads_triggered

async def check_for_updates():
    monitored = await get_monitored_animes()
    if not monitored: return []
    latest = await fetch_latest_releases()
    triggered = await process_releases(latest.items(), monitored)
    all_triggered = list(triggered)
    monitored = await get_monitored_animes()
    for _, pattern, _, _ in monitored:
        if not any(pattern.lower() in t.lower() for t in all_triggered):
            history = await search_anime_history(pattern)
            if history:
                deep_triggered = await process_releases(history, monitored)
                all_triggered.extend(deep_triggered)
                if deep_triggered: monitored = await get_monitored_animes()
    return all_triggered

async def force_download_subs():
    monitored = await get_monitored_animes()
    downloaded = []
    for _, pattern, last_ep, _ in monitored:
        if last_ep > 0:
            sub_file = await download_subtitle(pattern, last_ep)
            if sub_file: downloaded.append(f"{pattern} - {last_ep}")
    return downloaded
