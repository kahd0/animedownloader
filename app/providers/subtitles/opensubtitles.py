from __future__ import annotations
import re

import httpx

from app.models.subtitle import SubtitleResult
from app.providers.base import SubtitleProvider

_API = "https://api.opensubtitles.com/api/v1"
_STOPS = frozenset({"that", "this", "with", "from", "they", "will", "have", "been", "were", "after"})


class OpenSubtitlesProvider(SubtitleProvider):
    name = "opensubtitles"
    priority = 80

    def __init__(self, api_key: str = ""):
        self._api_key = api_key

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    async def search(self, title: str, episode: int) -> list[SubtitleResult]:
        if not self._api_key:
            return []
        # A API do OpenSubtitles exige os query params em ordem alfabética e em
        # minúsculas; caso contrário responde 301 para a URL canônica. Ordenar evita
        # o redirect, e follow_redirects cobre qualquer normalização extra do servidor.
        params = {
            "query": title.lower(),
            "episode_number": episode,
            "languages": "pt-br",
            "type": "episode",
        }
        try:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                resp = await client.get(
                    f"{_API}/subtitles",
                    params=sorted(params.items()),
                    headers={
                        "Api-Key": self._api_key,
                        "Content-Type": "application/json",
                        "User-Agent": "AnimeMonitor/1.0",
                    },
                    timeout=15,
                )
                if resp.status_code != 200:
                    print(f"[OpenSubtitles] HTTP {resp.status_code}: {resp.text[:200]}")
                    return []
                data = resp.json().get("data", [])
        except Exception as e:
            print(f"[OpenSubtitles] search erro: {e}")
            return []

        results = []
        for entry in data[:30]:
            attrs = entry.get("attributes", {})
            files = attrs.get("files", [])
            if not files:
                continue

            feature_title = attrs.get("feature_details", {}).get("title", "")
            release_name = attrs.get("release", "")
            if not _title_matches(title, feature_title, release_name):
                continue

            file_info = files[0]
            lang_code = (attrs.get("language", "") or "").lower()
            language = "pt-br" if lang_code in ("pt-br", "pt") else ("en" if lang_code == "en" else lang_code)
            fmt = (attrs.get("format") or "srt").lower()

            sub = SubtitleResult(
                provider=OpenSubtitlesProvider.name,
                language=language,
                filename=file_info.get("file_name", ""),
                format=fmt,
                episode=episode,
            )
            sub._dl_info = {
                "file_id": file_info.get("file_id"),
                "api_key": self._api_key,
            }
            results.append(sub)
        return results

    async def download(self, result: SubtitleResult) -> bytes:
        dl_info = getattr(result, "_dl_info", {})
        file_id = dl_info.get("file_id")
        api_key = dl_info.get("api_key") or self._api_key
        if not file_id or not api_key:
            raise ValueError("OpenSubtitles result missing file_id or api_key")

        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.post(
                f"{_API}/download",
                json={"file_id": file_id},
                headers={
                    "Api-Key": api_key,
                    "Content-Type": "application/json",
                    "User-Agent": "AnimeMonitor/1.0",
                },
                timeout=15,
            )
            resp.raise_for_status()
            link = resp.json().get("link")
            if not link:
                raise ValueError("OpenSubtitles returned no download link")
            resp2 = await client.get(link, timeout=30)
            resp2.raise_for_status()
            return resp2.content


def _title_words(text: str) -> set[str]:
    words = set(re.findall(r"[a-z]{4,}", text.lower()))
    return words - _STOPS


def _title_matches(series_name: str, candidate_title: str, release_name: str, threshold: float = 0.5) -> bool:
    query_words = _title_words(series_name)
    if len(query_words) < 2:
        return True
    for source in (candidate_title, release_name):
        if not source:
            continue
        result_words = _title_words(source)
        overlap = query_words & result_words
        if len(overlap) >= 2 and len(overlap) / len(query_words) >= threshold:
            return True
    return False
