"""Atualização de metadados (Jikan/MAL) dos animes monitorados."""
import asyncio

from app.core.database import get_monitored_animes, update_anime_metadata
from app.core.api import fetch_anime_metadata
from app.core.downloader.covers import download_cover


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
