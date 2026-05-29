"""Detecção de lançamentos: processa releases e dispara downloads de episódios novos."""
import asyncio
import os
import re

from app.core.config import get_final_dir, get_download_ahead, get_rss_feeds
from app.core.naming import matches_pattern
from app.core.database import (
    get_monitored_animes, mark_episode_queued, mark_episode_ready,
)
from app.core.api import (
    fetch_latest_releases, search_anime_history, fetch_rss_feed,
)
from app.utils.episode_parser import extract_episode_number
from app.core.downloader.subtitles import download_subtitle
from app.core.downloader.system import trigger_magnet


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
                        from app.core.events.bus import bus, EpisodeDetected
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
        db_last_ready = row[16] if len(row) > 16 else 0
        final_last_ready = max(db_last_ready, effective)
        row = (*row[:16], final_last_ready, *row[17:])
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
