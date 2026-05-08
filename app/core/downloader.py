import httpx
import re
import webbrowser
import platform
import subprocess
import os
import shutil
import asyncio
from .config import get_source_dir, get_final_dir, get_subs_dir, COVERS_DIR, get_download_ahead
from .naming import smart_rename, matches_pattern
from .database import get_monitored_animes, update_last_episode, update_anime_metadata
from .api import (
    fetch_latest_releases, search_anime_history, fetch_anime_metadata,
    find_subtitles, download_chosen_subtitle
)
from ..utils.episode_parser import extract_episode_number

_SUB_SORT_KEY = lambda s: (
    (0 if (s.get('info', {}).get('lang') == 'por'
           and 'forced' not in s.get('info', {}).get('desc', '').lower()
           and 'cc' not in s.get('info', {}).get('desc', '').lower())
     else 1 if s.get('info', {}).get('lang') == 'por'
     else 2 if s.get('info', {}).get('lang') == 'eng'
     else 3),
    0 if s.get('info', {}).get('codec', 'ass').lower() == 'ass' else 1,
    0 if s.get('source', 'animetosho') == 'animetosho' else 1,
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

        dir_files = await asyncio.to_thread(os.listdir, search_dir)
        videos = sorted(
            f for f in dir_files
            if f.lower().endswith(video_exts) and matches_pattern(f, pattern)
        )

        for video_file in videos:
            ep_num = extract_episode_number(video_file)
            if ep_num is None or ep_num in seen_eps:
                continue
            seen_eps.add(ep_num)

            video_path = os.path.join(search_dir, video_file)
            status = await asyncio.to_thread(check_subtitle_status, video_path)
            has_pt = "por" in (status.get("embedded_langs") or [])
            if has_pt:
                continue  # Embedded PT-BR exists — definitely correct, skip

            subs, series_name, ep_str = await find_subtitles(pattern, ep_num)
            subs.sort(key=_SUB_SORT_KEY)
            candidates.append({
                "pattern":     pattern,
                "last_ep":     ep_num,
                "subs":        subs,
                "series_name": series_name,
                "ep_str":      ep_str,
                "video_path":  video_path,
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
    await asyncio.to_thread(os.makedirs, final_dir, exist_ok=True)
    moved_files = []

    # 1. Mover vídeos da pasta de Downloads para a pasta FINAL
    if os.path.exists(source_dir):
        monitored = await get_monitored_animes()
        source_files = await asyncio.to_thread(os.listdir, source_dir)
        for filename in source_files:
            if filename.endswith((".!qB", ".part")): continue
            if not filename.lower().endswith((".mkv", ".mp4", ".avi")): continue

            for _, pattern, _, _, *_ in monitored:
                if matches_pattern(filename, pattern):
                    old_path = os.path.join(source_dir, filename)
                    new_name = smart_rename(filename)
                    new_path = os.path.join(final_dir, new_name)
                    try:
                        await asyncio.to_thread(shutil.move, old_path, new_path)
                        if new_name != filename:
                            moved_files.append(f"Renomeado: {filename} → {new_name}")
                        else:
                            moved_files.append(f"Vídeo: {filename}")
                    except Exception as e:
                        print(f"Erro ao mover vídeo {filename}: {e}")

    # 2. Parear legendas com vídeos na pasta FINAL
    subs_dir = get_subs_dir()
    if os.path.exists(subs_dir):
        final_files = await asyncio.to_thread(os.listdir, final_dir)
        subs_files = await asyncio.to_thread(os.listdir, subs_dir)
        final_set = set(final_files)

        for video_file in final_files:
            if not video_file.lower().endswith((".mkv", ".mp4", ".avi")): continue

            ep_num = extract_episode_number(video_file)
            if ep_num is None: continue
            ep_num_str = str(ep_num).zfill(2)

            video_name_no_ext = os.path.splitext(video_file)[0]
            has_sub = any(
                f.startswith(video_name_no_ext) and f.lower().endswith((".ass", ".srt"))
                for f in final_set
            )
            if has_sub: continue

            # Derive the expected subtitle prefix from the monitored pattern
            video_safe_prefix = None
            for _, pattern, *_ in monitored:
                if matches_pattern(video_file, pattern):
                    sname = re.sub(r's\d+|e\d+|-.*$|\d+p.*$', '', pattern, flags=re.I).strip()
                    video_safe_prefix = re.sub(r'[^\w\s-]', '', sname).strip().lower()
                    break

            for sub_file in subs_files:
                sub_lower = sub_file.lower()
                if f"_ep{ep_num_str}" not in sub_lower:
                    continue
                if video_safe_prefix and not sub_lower.startswith(video_safe_prefix):
                    continue
                    sub_ext = os.path.splitext(sub_file)[1]
                    old_sub_path = os.path.join(subs_dir, sub_file)
                    new_sub_name = f"{video_name_no_ext}{sub_ext}"
                    new_sub_path = os.path.join(final_dir, new_sub_name)
                    try:
                        await asyncio.to_thread(shutil.move, old_sub_path, new_sub_path)
                        final_set.add(new_sub_name)
                        moved_files.append(f"Legenda pareada: {video_file}")
                    except Exception as e:
                        print(f"Erro ao mover legenda {sub_file}: {e}")
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

    download_ahead = get_download_ahead()

    for info in normalized:
        show_name = info.get('show', '')
        try: episode_num = int(info.get('episode', 0))
        except (ValueError, TypeError):
            continue

        for row in monitored_list:
            anime_id        = row[0]
            pattern         = row[1]
            last_watched    = row[2]
            res             = row[3]
            last_downloaded = row[9]

            if pattern.lower() in show_name.lower() and last_downloaded < episode_num <= last_watched + download_ahead:
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
                    monitored_list = [
                        row[:9] + (episode_num,) if row[1] == pattern else row
                        for row in monitored_list
                    ]

    return downloads_triggered

async def check_for_updates():
    monitored = await get_monitored_animes()
    if not monitored:
        return []
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
                if deep_triggered:
                    monitored = await get_monitored_animes()

    from .config import get_rss_feeds
    from .api import fetch_rss_feed
    for feed in get_rss_feeds():
        if "{show}" in feed["url"]:
            for row in monitored:
                rss_releases = await fetch_rss_feed(feed["url"], row[1])
                if rss_releases:
                    rss_triggered = await process_releases(rss_releases, monitored)
                    all_triggered.extend(rss_triggered)
                    if rss_triggered:
                        monitored = await get_monitored_animes()
        else:
            rss_releases = await fetch_rss_feed(feed["url"])
            if rss_releases:
                rss_triggered = await process_releases(rss_releases, monitored)
                all_triggered.extend(rss_triggered)
                if rss_triggered:
                    monitored = await get_monitored_animes()

    return all_triggered

async def check_for_updates_single(anime_id: int, pattern: str):
    monitored = await get_monitored_animes()
    single = [row for row in monitored if row[0] == anime_id]
    if not single:
        return []
    latest = await fetch_latest_releases()
    triggered = await process_releases(latest.items(), single)
    if not triggered:
        history = await search_anime_history(pattern)
        if history:
            triggered = await process_releases(history, single)
    return triggered

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
