from __future__ import annotations
from typing import Any

import httpx

from app.providers.base import MetadataProvider

_JIKAN_API = "https://api.jikan.moe/v4"


class JikanProvider(MetadataProvider):
    """MyAnimeList metadata via Jikan API."""

    name = "jikan"

    async def fetch_metadata(self, title: str) -> dict[str, Any] | None:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{_JIKAN_API}/anime",
                    params={"q": title, "limit": 8},
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json().get("data", [])
                if not data:
                    return None
                item = next(
                    (d for d in data if d.get("status") == "Currently Airing"),
                    data[0],
                )
                return {
                    "official_title": item.get("title_english") or item.get("title"),
                    "cover_url": item.get("images", {}).get("jpg", {}).get("large_image_url"),
                    "airing_status": item.get("status"),
                    "mal_id": item.get("mal_id"),
                }
        except Exception as e:
            print(f"[Jikan] fetch_metadata erro: {e}")
            return None
