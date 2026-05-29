"""Seleção, busca e verificação de legendas dos episódios."""
import asyncio
import json
import os
import subprocess

from app.core.config import get_source_dir, get_final_dir
from app.core.naming import matches_pattern
from app.core.database import get_monitored_animes
from app.core.api import find_subtitles, download_chosen_subtitle
from app.utils.episode_parser import extract_episode_number

# Ordena candidatos de legenda: PT-BR não-forçada/não-CC primeiro, depois PT-BR,
# depois ENG; prioriza codec .ass e fontes que não sejam opensubtitles.
_SUB_SORT_KEY = lambda s: (
    (0 if (s.get('info', {}).get('lang') == 'por'
           and 'forced' not in s.get('info', {}).get('desc', '').lower()
           and 'cc' not in s.get('info', {}).get('desc', '').lower())
     else 1 if s.get('info', {}).get('lang') == 'por'
     else 2 if s.get('info', {}).get('lang') == 'eng'
     else 3),
    0 if s.get('info', {}).get('codec', 'ass').lower() == 'ass' else 1,
    0 if s.get('source') == 'opensubtitles' else 1,
)


async def download_subtitle(show_name, ep_num):
    """Seleciona automaticamente a melhor legenda PT-BR e baixa."""
    all_subs, series_name, ep_str = await find_subtitles(show_name, ep_num)
    if not all_subs:
        return None
    all_subs.sort(key=_SUB_SORT_KEY)
    return await download_chosen_subtitle(all_subs[0], series_name, ep_str)


async def force_download_subs():
    monitored = await get_monitored_animes()
    downloaded = []
    for _, pattern, last_ep, *_ in monitored:
        if last_ep > 0:
            sub_file = await download_subtitle(pattern, last_ep)
            if sub_file: downloaded.append(f"{pattern} - {last_ep}")
    return downloaded


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
            streams = json.loads(proc.stdout).get("streams", [])
            sub_streams = [s for s in streams if s.get("codec_type") == "subtitle"]
            if sub_streams:
                result["embedded"] = True
                result["embedded_langs"] = [
                    s.get("tags", {}).get("language", "und") for s in sub_streams
                ]
    except Exception:
        pass

    return result
