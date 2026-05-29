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
from .database import get_monitored_animes, update_last_episode, mark_episode_queued, mark_episode_ready, update_anime_metadata
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
    0 if s.get('source') == 'opensubtitles' else 1,
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

_ASS_TAG_RE = re.compile(r'\{[^}]*\}')
_ASS_NEWLINE_RE = re.compile(r'\\[Nnh]')
_GTRANSLATE_URL = "https://translate.googleapis.com/translate_a/single"


async def _extract_source_ass(video_path, tmp_path):
    """Obtém o .ass de origem: usa externo se existir, senão extrai do vídeo via ffmpeg."""
    base = os.path.splitext(video_path)[0]
    for ext in (".ass", ".ssa"):
        if os.path.exists(base + ext):
            return base + ext, False
    if os.path.exists(base + ".srt"):
        proc = await asyncio.to_thread(
            subprocess.run,
            ["ffmpeg", "-y", "-i", base + ".srt", "-c:s", "ass", tmp_path],
            capture_output=True, text=True,
        )
        if proc.returncode == 0 and os.path.exists(tmp_path):
            return tmp_path, True
        return None, False

    proc = await asyncio.to_thread(
        subprocess.run,
        ["ffmpeg", "-y", "-i", video_path, "-map", "0:s:0", "-c:s", "ass", tmp_path],
        capture_output=True, text=True,
    )
    if proc.returncode == 0 and os.path.exists(tmp_path):
        return tmp_path, True
    return None, False


def _protect_ass_text(text):
    """Substitui tags ASS e quebras de linha por placeholders preservados na tradução."""
    tokens = []
    def _save(m):
        tokens.append(m.group(0))
        return f"[[[{len(tokens) - 1}]]]"
    protected = _ASS_TAG_RE.sub(_save, text)
    protected = _ASS_NEWLINE_RE.sub(_save, protected)
    return protected, tokens


def _restore_ass_text(text, tokens):
    for i, t in enumerate(tokens):
        text = text.replace(f"[[[{i}]]]", t)
    return text


async def _translate_one(client, sem, text):
    if not text.strip():
        return text
    async with sem:
        params = {
            "client": "gtx",
            "sl": "auto",
            "tl": "pt",
            "dt": "t",
            "q": text,
        }
        for attempt in range(3):
            try:
                resp = await client.get(_GTRANSLATE_URL, params=params, timeout=20.0)
                if resp.status_code == 200:
                    data = resp.json()
                    chunks = data[0] or []
                    return "".join(c[0] for c in chunks if c and c[0])
                if resp.status_code == 429:
                    await asyncio.sleep(2 + attempt * 2)
                    continue
                return text
            except Exception:
                await asyncio.sleep(1 + attempt)
        return text


async def translate_video_subtitle(video_path):
    """Traduz a legenda do vídeo para PT-BR de forma controlada."""
    if not os.path.exists(video_path):
        return {"ok": False, "output_path": None, "error": f"Arquivo não encontrado: {video_path}"}

    from .config import get_gemini_api_key
    gemini_key = get_gemini_api_key()

    expected_output = os.path.splitext(video_path)[0] + ".pt.ass"
    tmp_src = expected_output + ".src.tmp.ass"

    src_path, is_tmp = await _extract_source_ass(video_path, tmp_src)
    if not src_path:
        return {"ok": False, "output_path": None, "error": "Não foi possível obter a legenda de origem (sem .ass/.srt externo nem stream embutido)"}

    try:
        raw = await asyncio.to_thread(_read_text_with_fallback, src_path)
    except Exception as e:
        if is_tmp and os.path.exists(tmp_src):
            try: os.remove(tmp_src)
            except Exception: pass
        return {"ok": False, "output_path": None, "error": f"Falha ao ler legenda de origem: {e}"}

    lines = raw.splitlines()
    dialogue_indices = []
    texts_to_translate = []
    token_sets = []

    for idx, line in enumerate(lines):
        if not line.startswith("Dialogue:"):
            continue
        parts = line.split(",", 9)
        if len(parts) < 10:
            continue
        protected, tokens = _protect_ass_text(parts[9])
        dialogue_indices.append((idx, parts))
        texts_to_translate.append(protected)
        token_sets.append(tokens)

    if not texts_to_translate:
        if is_tmp and os.path.exists(tmp_src):
            try: os.remove(tmp_src)
            except Exception: pass
        return {"ok": False, "output_path": None, "error": "Nenhuma linha de diálogo encontrada na legenda"}

    if gemini_key:
        from ..providers.translators.gemini import GeminiProvider
        provider = GeminiProvider(api_key=gemini_key)
        
        translated = []
        chunk_size = 30
        for i in range(0, len(texts_to_translate), chunk_size):
            chunk = texts_to_translate[i:i + chunk_size]
            success = False
            for attempt in range(4):
                try:
                    chunk_trans = await provider.translate_batch(chunk)
                    if (chunk_trans == chunk and any(re.search('[a-zA-Z]', c) for c in chunk)) or not chunk_trans:
                        if attempt < 3:
                            await asyncio.sleep(15 + attempt * 10)
                            continue
                        break
                    translated.extend(chunk_trans)
                    success = True
                    break
                except Exception:
                    if attempt < 3: await asyncio.sleep(15 + attempt * 10)
                    else: break
            
            if not success:
                sem = asyncio.Semaphore(8)
                async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0"}) as client:
                    chunk_fallback = await asyncio.gather(*(_translate_one(client, sem, t) for t in chunk))
                    translated.extend(chunk_fallback)
            
            await asyncio.sleep(4.5)
    else:
        sem = asyncio.Semaphore(8)
        async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0"}) as client:
            translated = await asyncio.gather(*(_translate_one(client, sem, t) for t in texts_to_translate))

    for (idx, parts), trans_text, tokens in zip(dialogue_indices, translated, token_sets):
        parts[9] = _restore_ass_text(trans_text, tokens)
        lines[idx] = ",".join(parts)

    try:
        def _write_output():
            with open(expected_output, "w", encoding="utf-8") as _f:
                _f.write("\n".join(lines))
        await asyncio.to_thread(_write_output)
    except Exception as e:
        if is_tmp and os.path.exists(tmp_src):
            try: os.remove(tmp_src)
            except Exception: pass
        return {"ok": False, "output_path": None, "error": f"Falha ao escrever .pt.ass: {e}"}

    if is_tmp and os.path.exists(tmp_src):
        try: os.remove(tmp_src)
        except Exception: pass

    return {"ok": True, "output_path": expected_output, "error": None}


def _read_text_with_fallback(path):
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()

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
    monitored = await get_monitored_animes()
    if os.path.exists(source_dir):

        def _get_files():
            files = []
            final_abs = os.path.abspath(final_dir)
            for root, _, fs in os.walk(source_dir):
                root_abs = os.path.abspath(root)
                # Evita recursão na pasta final se ela estiver dentro de source_dir
                if root_abs == final_abs or root_abs.startswith(final_abs + os.sep):
                    continue
                for f in fs:
                    files.append((f, os.path.join(root, f)))
            return files

        source_files = await asyncio.to_thread(_get_files)

        for filename, old_path in source_files:
            if filename.endswith((".!qB", ".part")): continue
            if not filename.lower().endswith((".mkv", ".mp4", ".avi")): continue

            for row in monitored:
                pattern = row[1]
                if matches_pattern(filename, pattern):
                    new_name = smart_rename(filename)
                    new_path = os.path.join(final_dir, new_name)
                    try:
                        await asyncio.to_thread(shutil.move, old_path, new_path)
                        if new_name != filename:
                            moved_files.append(f"Renomeado: {filename} → {new_name}")
                        else:
                            moved_files.append(f"Vídeo: {filename}")

                        # Mark episode as ready on disk (update last_ready in DB)
                        ep_num = extract_episode_number(new_name)
                        if ep_num is not None:
                            await mark_episode_ready(pattern, ep_num)

                        # Limpa pasta de origem se ficou vazia e não é a pasta raiz
                        old_dir = os.path.dirname(old_path)
                        if os.path.abspath(old_dir) != os.path.abspath(source_dir):
                            if not os.listdir(old_dir):
                                os.rmdir(old_dir)
                    except Exception as e:
                        print(f"Erro ao mover vídeo {filename}: {e}")
                    break

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
                sub_lower = sub_file.lower().replace("_", " ")
                if f" ep{ep_num_str}" not in sub_lower:
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
            # last_ready reflects episodes actually confirmed on disk; use it as
            # the re-download threshold so episodes queued but never moved to disk
            # get re-triggered on the next "Verificar agora".
            last_ready      = row[16] if len(row) > 16 else last_downloaded

            window_base = max(last_watched, last_downloaded)
            if matches_pattern(show_name, pattern) and last_ready < episode_num <= window_base + download_ahead:
                magnet = None
                for dl in info.get('downloads', []):
                    if dl.get('res') == res.replace('p', ''):
                        magnet = dl.get('magnet'); break

                if not magnet and info.get('downloads'): magnet = info['downloads'][0].get('magnet')

                if magnet:
                    await mark_episode_queued(pattern, episode_num)
                    # Emit event so the pipeline takes over (qBittorrent + subtitle + organizer)
                    try:
                        from ..core.events.bus import bus, EpisodeDetected
                        await bus.publish(EpisodeDetected(
                            anime_id=anime_id,
                            title_pattern=pattern,
                            episode=episode_num,
                            magnet=magnet,
                            resolution=res,
                            source="subsplease",
                        ))
                    except Exception:
                        # Fallback: direct magnet open (pipeline not set up)
                        trigger_magnet(magnet)
                        await mark_episode_ready(pattern, episode_num)
                        sub_file = await download_subtitle(show_name, episode_num)
                        sub_msg = " (Legenda baixada)" if sub_file else ""
                        downloads_triggered.append(f"{show_name} - {episode_num} ({res}){sub_msg}")
                    else:
                        downloads_triggered.append(f"{show_name} - {episode_num} ({res}) [pipeline]")
                    monitored_list = [
                        (*row[:9], episode_num, *row[10:]) if row[1] == pattern else row
                        for row in monitored_list
                    ]

    return downloads_triggered

async def _disk_last_ready(monitored: list) -> dict[str, int]:
    """Return {title_pattern: highest_ep_on_disk} by scanning the final episodes folder.

    This is used to override the DB last_ready value, which can become stale when
    the pipeline marks episodes ready before the file is actually organized to disk.
    """
    final_dir = get_final_dir()
    if not os.path.isdir(final_dir):
        return {}
    try:
        files = await asyncio.to_thread(os.listdir, final_dir)
    except Exception:
        return {}
    exts = {".mkv", ".mp4", ".avi", ".mov", ".wmv"}
    video_eps = [
        (f, extract_episode_number(f))
        for f in files if os.path.splitext(f)[1].lower() in exts
    ]
    result = {}
    for row in monitored:
        pattern = row[1]
        matching = [ep for f, ep in video_eps if ep is not None and matches_pattern(f, pattern)]
        result[pattern] = max(matching) if matching else 0
    return result


def _with_disk_last_ready(monitored: list, disk_map: dict[str, int]) -> list:
    """Return monitored rows with last_ready (index 16) clamped to the disk-based value.

    Uses max(last_watched, disk_val) so already-watched episodes (no longer on disk)
    are never re-downloaded — only episodes after the last watched are triggered.
    """
    patched = []
    for row in monitored:
        pattern   = row[1]
        last_watched = int(row[2] or 0)
        disk_val  = disk_map.get(pattern, 0)
        # Effective threshold: don't re-trigger anything the user has already watched,
        # even if the file was deleted from disk.
        effective = max(last_watched, disk_val)
        if len(row) > 16 and row[16] > effective:
            row = (*row[:16], effective, *row[17:])
        patched.append(row)
    return patched


async def check_for_updates():
    monitored = await get_monitored_animes()
    if not monitored:
        return []
    disk_map = await _disk_last_ready(monitored)
    monitored = _with_disk_last_ready(monitored, disk_map)
    latest = await fetch_latest_releases()
    triggered = await process_releases(latest.items(), monitored)
    all_triggered = list(triggered)
    monitored = _with_disk_last_ready(await get_monitored_animes(), disk_map)
    for _, pattern, *_ in monitored:
        # Check if any triggered string matches this pattern, including shows
        # whose SubsPlease title differs from the monitored pattern (e.g. Japanese titles).
        already_triggered = any(
            matches_pattern(t.split(' - ')[0], pattern) for t in all_triggered if ' - ' in t
        )
        if not already_triggered:
            history = await search_anime_history(pattern)
            # If full-title search returns nothing, try each distinctive word.
            # Only accept a word's results if at least one entry actually matches
            # the pattern — avoids accepting "Release that Witch" when looking for
            # "Witch Hat Atelier" which lives under the Japanese title on SubsPlease.
            if not history:
                words = re.findall(r'[a-z]{5,}', pattern.lower())
                for word in words:
                    candidate = list(await search_anime_history(word))
                    matched_show = next(
                        ((c[1] if isinstance(c, tuple) else c).get('show', '')
                         for c in candidate
                         if matches_pattern((c[1] if isinstance(c, tuple) else c).get('show', ''), pattern)),
                        None,
                    )
                    if matched_show:
                        # Only keep episodes from the single matched show to avoid
                        # false positives from other shows sharing the search keyword.
                        history = [
                            c for c in candidate
                            if (c[1] if isinstance(c, tuple) else c).get('show', '') == matched_show
                        ]
                        break
            if history:
                deep_triggered = await process_releases(history, monitored)
                all_triggered.extend(deep_triggered)
                if deep_triggered:
                    monitored = _with_disk_last_ready(await get_monitored_animes(), disk_map)

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
                        monitored = _with_disk_last_ready(await get_monitored_animes(), disk_map)
        else:
            rss_releases = await fetch_rss_feed(feed["url"])
            if rss_releases:
                rss_triggered = await process_releases(rss_releases, monitored)
                all_triggered.extend(rss_triggered)
                if rss_triggered:
                    monitored = _with_disk_last_ready(await get_monitored_animes(), disk_map)

    return all_triggered

async def check_for_updates_single(anime_id: int, pattern: str):
    monitored = await get_monitored_animes()
    single = [row for row in monitored if row[0] == anime_id]
    if not single:
        return []
    disk_map = await _disk_last_ready(single)
    single = _with_disk_last_ready(single, disk_map)
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
            anime_id, meta["official_title"], meta["cover_url"], meta["airing_status"],
            total_episodes=meta.get("total_episodes"),
            score=meta.get("score"),
            studio=meta.get("studio"),
            season=meta.get("season"),
            mal_year=meta.get("mal_year"),
            synopsis=meta.get("synopsis"),
        )
        if meta.get("cover_url"):
            await download_cover(meta["cover_url"], title_pattern)
    return meta

async def refresh_all_metadata():
    monitored = await get_monitored_animes()
    updated = []
    for row in monitored:
        anime_id, pattern = row[0], row[1]
        meta = await fetch_anime_metadata(pattern)
        if meta:
            await update_anime_metadata(
                anime_id, meta["official_title"], meta["cover_url"], meta["airing_status"],
                total_episodes=meta.get("total_episodes"),
                score=meta.get("score"),
                studio=meta.get("studio"),
                season=meta.get("season"),
                mal_year=meta.get("mal_year"),
                synopsis=meta.get("synopsis"),
            )
            updated.append(pattern)
        await asyncio.sleep(0.4)  # Jikan rate limit
    return updated
