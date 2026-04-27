import httpx
import re
import webbrowser
import platform
import subprocess
import os
import shutil
import asyncio
from .config import get_source_dir, get_final_dir, get_subs_dir, COVERS_DIR
from .naming import smart_rename, matches_pattern
from .database import get_monitored_animes, update_last_episode, update_anime_metadata
from .api import (
    fetch_latest_releases, search_anime_history, fetch_anime_metadata,
    find_subtitles, download_chosen_subtitle
)

_SUB_SORT_KEY = lambda s: (
    0 if (s.get('info', {}).get('lang') == 'por'
          and 'forced' not in s.get('info', {}).get('desc', '').lower()
          and 'cc' not in s.get('info', {}).get('desc', '').lower())
    else 1 if s.get('info', {}).get('lang') == 'por'
    else 2 if s.get('info', {}).get('lang') == 'eng'
    else 3
)

async def search_subsplease_shows(query):
    """Retorna nomes únicos de shows disponíveis no SubsPlease para a query."""
    items = await search_anime_history(query)
    seen, shows = set(), []
    for item in items:
        info = item[1] if isinstance(item, tuple) else item
        name = info.get('show', '') if isinstance(info, dict) else ''
        if name and name not in seen:
            seen.add(name)
            shows.append(name)
    return shows

async def download_cover(url, title_pattern):
    """Baixa a imagem da capa e salva em covers/. Retorna o path local ou None."""
    safe = re.sub(r'[^\w\s-]', '', title_pattern).strip().lower().replace(' ', '_')
    path = os.path.join(COVERS_DIR, f"{safe}.jpg")
    if os.path.exists(path):
        return path
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, timeout=10)
            resp.raise_for_status()
            os.makedirs(COVERS_DIR, exist_ok=True)
            with open(path, 'wb') as f:
                f.write(resp.content)
            return path
        except Exception as e:
            print(f"Erro ao baixar capa: {e}")
            return None

async def download_subtitle(show_name, ep_num):
    """Seleciona automaticamente a melhor legenda PT-BR e baixa."""
    all_subs, series_name, ep_str = await find_subtitles(show_name, ep_num)
    if not all_subs:
        return None
    all_subs.sort(key=_SUB_SORT_KEY)
    return await download_chosen_subtitle(all_subs[0], series_name, ep_str)

async def get_subtitle_candidates():
    """Retorna candidatos de legenda para todos os animes monitorados (seleção manual)."""
    monitored = await get_monitored_animes()
    candidates = []
    for row in monitored:
        pattern, last_ep = row[1], row[2]
        if last_ep <= 0:
            continue
        subs, series_name, ep_str = await find_subtitles(pattern, last_ep)
        candidates.append({
            "pattern":     pattern,
            "last_ep":     last_ep,
            "subs":        subs,
            "series_name": series_name,
            "ep_str":      ep_str,
        })
    return candidates

async def get_subtitle_candidates_for_anime(pattern):
    """Busca candidatos de legenda para todos os eps sem legenda de um anime."""
    video_exts = (".mkv", ".mp4", ".avi")
    seen_eps: set[int] = set()
    candidates = []
    
    source_dir = get_source_dir()
    final_dir = get_final_dir()

    for search_dir in (final_dir, source_dir):
        if not os.path.exists(search_dir):
            continue

        videos = sorted(
            f for f in os.listdir(search_dir)
            if f.lower().endswith(video_exts) and matches_pattern(f, pattern)
        )

        for video_file in videos:
            m = re.search(r'[Ss]\d+[Ee](\d+)', video_file) or re.search(r'(?:[\s-])0?(\d+)(?:\D|$)', video_file)
            if not m:
                continue
            ep_num = int(m.group(1))
            if ep_num in seen_eps:
                continue
            seen_eps.add(ep_num)

            status = check_subtitle_status(os.path.join(search_dir, video_file))
            has_pt = "por" in (status.get("embedded_langs") or [])
            if status["external"] or has_pt:
                continue

            subs, series_name, ep_str = await find_subtitles(pattern, ep_num)
            candidates.append({
                "pattern":     pattern,
                "last_ep":     ep_num,
                "subs":        subs,
                "series_name": series_name,
                "ep_str":      ep_str,
            })

    return candidates

def check_subtitle_status(video_path):
    """Verifica legendas externas e embutidas (via ffprobe) de um arquivo de vídeo."""
    import json as _json
    result = {"external": None, "embedded": False, "embedded_langs": []}

    base = os.path.splitext(video_path)[0]
    for ext in (".ass", ".srt", ".sub"):
        if os.path.exists(base + ext):
            result["external"] = os.path.basename(base + ext)
            break

    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", video_path],
            capture_output=True, text=True, timeout=5,
        )
        if proc.returncode == 0:
            streams = _json.loads(proc.stdout).get("streams", [])
            sub_streams = [s for s in streams if s.get("codec_type") == "subtitle"]
            if sub_streams:
                result["embedded"] = True
                result["embedded_langs"] = [
                    s.get("tags", {}).get("language", "und") for s in sub_streams
                ]
    except Exception:
        pass

    return result

def open_path(path):
    """Abre um arquivo ou pasta com o aplicativo padrão do sistema."""
    try:
        if platform.system() == "Windows": os.startfile(path)
        elif platform.system() == "Darwin": subprocess.run(["open", path])
        else: subprocess.run(["xdg-open", path])
        return True
    except Exception as e:
        print(f"Erro ao abrir {path}: {e}")
        return False

def trigger_magnet(magnet_link):
    try:
        return open_path(magnet_link)
    except Exception as e:
        print(f"Erro ao abrir magnet: {e}")
        return webbrowser.open(magnet_link)

async def organize_downloads():
    """Move vídeos e busca legendas correspondentes"""
    source_dir = get_source_dir()
    final_dir = get_final_dir()
    os.makedirs(final_dir, exist_ok=True)
    moved_files = []

    # 1. Mover vídeos da pasta de Downloads para a pasta FINAL
    if os.path.exists(source_dir):
        monitored = await get_monitored_animes()
        for filename in os.listdir(source_dir):
            if filename.endswith((".!qB", ".part")): continue
            if not filename.lower().endswith((".mkv", ".mp4", ".avi")): continue

            for _, pattern, _, _, *_ in monitored:
                if matches_pattern(filename, pattern):
                    old_path = os.path.join(source_dir, filename)
                    new_name = smart_rename(filename)
                    new_path = os.path.join(final_dir, new_name)
                    try:
                        shutil.move(old_path, new_path)
                        if new_name != filename:
                            moved_files.append(f"Renomeado: {filename} → {new_name}")
                        else:
                            moved_files.append(f"Vídeo: {filename}")
                    except Exception as e:
                        print(f"Erro ao mover vídeo {filename}: {e}")

    # 2. Parear legendas com vídeos na pasta FINAL
    if os.path.exists(get_subs_dir()):
        for video_file in os.listdir(final_dir):
            if not video_file.lower().endswith((".mkv", ".mp4", ".avi")): continue
            
            ep_match = re.search(r'S\d+E(\d+)', video_file, re.I)
            if ep_match:
                ep_num = ep_match.group(1).zfill(2)
            else:
                ep_match = re.search(r'(?:[\s-])0?(\d+)(?:\D|$)', video_file)
                if not ep_match: continue
                ep_num = ep_match.group(1).zfill(2)
            video_name_no_ext = os.path.splitext(video_file)[0]
            
            has_sub = any(video_name_no_ext in f and f.lower().endswith((".ass", ".srt")) for f in os.listdir(final_dir))
            if has_sub: continue

            for sub_file in os.listdir(get_subs_dir()):
                if f"_ep{ep_num}" in sub_file.lower():
                    sub_ext = os.path.splitext(sub_file)[1]
                    old_sub_path = os.path.join(get_subs_dir(), sub_file)
                    new_sub_path = os.path.join(final_dir, f"{video_name_no_ext}{sub_ext}")
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

        for anime_id, pattern, last_ep, res, *_ in monitored_list:
            if pattern.lower() in show_name.lower() and episode_num > last_ep:
                magnet = None
                for dl in info.get('downloads', []):
                    if dl.get('res') == res.replace('p', ''):
                        magnet = dl.get('magnet'); break
                
                if not magnet and info.get('downloads'): magnet = info['downloads'][0].get('magnet')

                if magnet and trigger_magnet(magnet):
                    await update_last_episode(pattern, episode_num)
                    sub_file = await download_subtitle(show_name, episode_num)
                    sub_msg = " (Legenda baixada)" if sub_file else " (Legenda não encontrada ainda)"
                    downloads_triggered.append(f"{show_name} - {episode_num} ({res}){sub_msg}")
                    monitored_list = [(aid, p, episode_num if p == pattern else lep, r, *rest) for aid, p, lep, r, *rest in monitored_list]
    
    return downloads_triggered

async def check_for_updates():
    monitored = await get_monitored_animes()
    if not monitored: return []
    latest = await fetch_latest_releases()
    triggered = await process_releases(latest.items(), monitored)
    all_triggered = list(triggered)
    monitored = await get_monitored_animes()
    for _, pattern, *_ in monitored:
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
    for _, pattern, last_ep, *_ in monitored:
        if last_ep > 0:
            sub_file = await download_subtitle(pattern, last_ep)
            if sub_file: downloaded.append(f"{pattern} - {last_ep}")
    return downloaded

async def refresh_single_metadata(anime_id: int, title_pattern: str):
    meta = await fetch_anime_metadata(title_pattern)
    if meta:
        await update_anime_metadata(
            anime_id, meta["official_title"], meta["cover_url"], meta["airing_status"]
        )
    return meta

async def refresh_all_metadata():
    monitored = await get_monitored_animes()
    updated = []
    for row in monitored:
        anime_id, pattern = row[0], row[1]
        meta = await fetch_anime_metadata(pattern)
        if meta:
            await update_anime_metadata(
                anime_id, meta["official_title"], meta["cover_url"], meta["airing_status"]
            )
            updated.append(pattern)
        await asyncio.sleep(0.4)  # Jikan rate limit
    return updated
