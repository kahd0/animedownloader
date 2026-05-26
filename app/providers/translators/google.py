from __future__ import annotations
import asyncio
import urllib.parse

import httpx

from app.providers.base import TranslatorProvider

_TRANSLATE_URL = "https://translate.googleapis.com/translate_a/single"
_MAX_CONCURRENT = 8


class GoogleTranslateProvider(TranslatorProvider):
    """Google Translate without API key (public endpoint). Rate-limited."""

    name = "google"

    async def translate_batch(
        self,
        texts: list[str],
        source_lang: str = "ja",
        target_lang: str = "pt",
    ) -> list[str]:
        sem = asyncio.Semaphore(_MAX_CONCURRENT)
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:
            tasks = [_translate_one(client, sem, text, source_lang, target_lang) for text in texts]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        translated = []
        for orig, result in zip(texts, results):
            if isinstance(result, Exception):
                print(f"[Google] translate erro: {result}")
                translated.append(orig)
            else:
                translated.append(result)
        return translated


async def _translate_one(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    text: str,
    source_lang: str,
    target_lang: str,
    max_retries: int = 3,
) -> str:
    if not text.strip():
        return text

    async with sem:
        for attempt in range(max_retries):
            try:
                resp = await client.get(
                    _TRANSLATE_URL,
                    params={
                        "client": "gtx",
                        "sl": source_lang,
                        "tl": target_lang,
                        "dt": "t",
                        "q": text,
                    },
                )
                if resp.status_code == 429:
                    wait = 2 ** attempt
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                data = resp.json()
                parts = [seg[0] for seg in (data[0] or []) if seg and seg[0]]
                return "".join(parts)
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(1)
        return text
