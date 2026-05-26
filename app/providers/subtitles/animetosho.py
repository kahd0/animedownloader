from __future__ import annotations
import asyncio
import lzma
import os
import re

import httpx

from app.models.subtitle import SubtitleResult
from app.providers.base import SubtitleProvider

_API = "https://animetosho.org/api"


class AnimeToshoProvider(SubtitleProvider):
    name = "animetosho"
    priority = 60

    async def search(self, title: str, episode: int) -> list[SubtitleResult]:
        ep_str = str(episode).zfill(2)
        ep_regex = _make_ep_regex(episode)
        queries = [
            f"{title} {ep_str}",
            f"{title} pt-br {ep_str}",
            f"{title} Brazilian {ep_str}",
        ]
        all_subs: list[SubtitleResult] = []
        seen_ids: set[int] = set()

        async with httpx.AsyncClient() as client:
            for q in queries:
                try:
                    resp = await client.get(_API, params={"q": q}, timeout=10)
                    if not resp.content:
                        continue
                    data = resp.json()
                    if not data or not isinstance(data, list):
                        continue
                    matching = [e for e in data[:10] if e and ep_regex.search(e.get("title", ""))]
                    if not matching:
                        continue
                    results = await asyncio.gather(
                        *[_fetch_entry(client, e["id"], ep_regex, seen_ids, title, ep_str) for e in matching],
                        return_exceptions=True,
                    )
                    for r in results:
                        if isinstance(r, list):
                            all_subs.extend(r)
                except Exception as e:
                    print(f"[AnimeTosho] search erro ({q}): {e}")

        return all_subs

    async def download(self, result: SubtitleResult) -> bytes:
        attach_id = result._dl_info.get("id") if hasattr(result, "_dl_info") else None
        if attach_id is None:
            raise ValueError("AnimeTosho result missing attachment id")
        url = f"https://storage.animetosho.org/attach/{attach_id:08x}/file.xz"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=15)
            resp.raise_for_status()
            return lzma.decompress(resp.content)


async def _fetch_entry(
    client: httpx.AsyncClient,
    entry_id: int,
    ep_regex: re.Pattern,
    seen_ids: set[int],
    series_name: str,
    ep_str: str,
) -> list[SubtitleResult]:
    try:
        resp = await client.get(_API, params={"show": "torrent", "id": entry_id}, timeout=10)
        if not resp.content:
            return []
        det = resp.json()
        if not det or not isinstance(det, dict):
            return []

        results = []
        for f in det.get("files", []):
            if not f or not ep_regex.search(f.get("filename", "")):
                continue
            parent_stem = os.path.splitext(f.get("filename", ""))[0]
            for a in f.get("attachments", []):
                if a.get("type") != "subtitle" or not a.get("id") or a["id"] in seen_ids:
                    continue
                attach_fname = a.get("filename", "")
                if attach_fname and re.search(r"[-\s]\d{2}(?:[^p\d]|$)", attach_fname):
                    if not ep_regex.search(attach_fname):
                        continue

                display_name = attach_fname or parent_stem or f"{series_name} - Ep {ep_str}"
                info = a.get("info", {})
                lang_raw = info.get("lang", "")
                if not lang_raw:
                    lang_raw = _lang_from_filename(attach_fname)

                language = _normalize_lang(lang_raw)
                fmt = (info.get("codec") or "ass").lower()

                sub = SubtitleResult(
                    provider=AnimeToshoProvider.name,
                    language=language,
                    filename=display_name,
                    format=fmt,
                    episode=int(ep_str) if ep_str.isdigit() else None,
                )
                sub._dl_info = {"id": a["id"]}
                seen_ids.add(a["id"])
                results.append(sub)
        return results
    except Exception as e:
        print(f"[AnimeTosho] entry erro ({entry_id}): {e}")
        return []


def _make_ep_regex(ep_num: int) -> re.Pattern:
    return re.compile(rf"(?:[\s\-_]|[Ee]p?)0*{ep_num}(?:\D|$)")


def _lang_from_filename(filename: str) -> str:
    f = filename.lower()
    if any(t in f for t in ("pt-br", "ptbr", "portuguese", "brasil", ".por.", "_por_")):
        return "por"
    if any(t in f for t in (".eng.", "_eng_", "english")):
        return "eng"
    return ""


def _normalize_lang(raw: str) -> str:
    r = raw.lower()
    if r in ("por", "pt-br", "pt", "portuguese", "brasil"):
        return "pt-br"
    if r in ("eng", "en", "english"):
        return "en"
    if r in ("jpn", "ja", "japanese"):
        return "ja"
    return raw or "unknown"
