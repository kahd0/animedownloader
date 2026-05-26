from __future__ import annotations
import io
import re
import xml.etree.ElementTree as ET
from datetime import datetime

import httpx

from app.models.release import Release
from app.providers.base import RSSProvider
from app.utils.episode_parser import extract_episode_number


_API_URL = "https://subsplease.org/api/?f=latest&h=true&tz=UTC"
_SEARCH_URL = "https://subsplease.org/api/?f=search&tz=UTC&s="
_RSS_URL = "https://subsplease.org/rss/?r=1080"


class SubsPleaseProvider(RSSProvider):
    name = "SubsPlease"

    async def fetch_releases(self, show_name: str) -> list[Release]:
        """Fetch releases for a specific show from SubsPlease RSS."""
        url = f"{_RSS_URL}&t={show_name.replace(' ', '+')}"
        return await _parse_rss_url(url, self.name)

    async def fetch_all_latest(self) -> list[Release]:
        """Fetch all currently airing releases from SubsPlease API."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(_API_URL, timeout=15)
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            print(f"[SubsPlease] fetch_all_latest erro: {e}")
            return []

        releases = []
        for show_name, entry in data.items():
            ep = entry.get("episode")
            ep_num = extract_episode_number(str(ep)) if ep else None
            for res, dl in (entry.get("downloads") or {}).items():
                magnet = dl.get("magnet", "")
                if not magnet:
                    continue
                releases.append(Release(
                    title=show_name,
                    normalized_title=show_name,
                    episode=ep_num,
                    season=1,
                    resolution=f"{res}p" if not res.endswith("p") else res,
                    source=self.name,
                    magnet=magnet,
                    published_at=datetime.utcnow(),
                ))
        return releases

    async def search_history(self, query: str) -> list[dict]:
        """Search SubsPlease history — returns raw API dicts for backward compat."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{_SEARCH_URL}{query}", timeout=15)
                resp.raise_for_status()
                data = resp.json()
                return list(data.items()) if isinstance(data, dict) else []
        except Exception as e:
            print(f"[SubsPlease] search_history erro: {e}")
            return []


async def _parse_rss_url(url: str, source_name: str) -> list[Release]:
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=15, follow_redirects=True)
            resp.raise_for_status()
            content = resp.text
    except Exception as e:
        print(f"[RSS] fetch erro ({url}): {e}")
        return []

    try:
        ns_map: dict[str, str] = {}
        for event, elem in ET.iterparse(io.StringIO(content), events=["start-ns"]):
            ns_map[elem[0]] = elem[1]
        root = ET.fromstring(content)
    except ET.ParseError as e:
        print(f"[RSS] parse erro ({url}): {e}")
        return []

    releases = []
    for item in root.findall(".//item"):
        title_el = item.find("title")
        if title_el is None:
            continue
        title = title_el.text or ""
        ep_num = extract_episode_number(title)
        if ep_num is None:
            continue

        magnet = _extract_magnet(item, ns_map)
        if not magnet:
            continue

        res_match = re.search(r"(\d{3,4})p", title, re.IGNORECASE)
        resolution = f"{res_match.group(1)}p" if res_match else "1080p"

        group_match = re.match(r"^\[([^\]]+)\]", title)
        release_group = group_match.group(1) if group_match else None

        releases.append(Release(
            title=title,
            normalized_title=_strip_title(title),
            episode=ep_num,
            season=1,
            resolution=resolution,
            source=source_name,
            magnet=magnet,
            release_group=release_group,
            published_at=datetime.utcnow(),
        ))
    return releases


def _extract_magnet(item: ET.Element, ns_map: dict[str, str]) -> str | None:
    for uri in ns_map.values():
        el = item.find(f"{{{uri}}}magnet")
        if el is not None and el.text and el.text.startswith("magnet:"):
            return el.text
    enc = item.find("enclosure")
    if enc is not None:
        u = enc.get("url", "")
        if u.startswith("magnet:"):
            return u
    link_el = item.find("link")
    if link_el is not None and link_el.text and link_el.text.startswith("magnet:"):
        return link_el.text
    return None


def _strip_title(title: str) -> str:
    name = re.sub(r"^\[[^\]]+\]\s*", "", title)
    name = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", name)
    name = re.sub(r"\s*-\s*\d+\s*$", "", name)
    return name.strip()
