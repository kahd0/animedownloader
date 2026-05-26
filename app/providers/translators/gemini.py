from __future__ import annotations
import asyncio
import json

import httpx

from app.providers.base import TranslatorProvider

_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
_BATCH_SIZE = 50
_SYSTEM_PROMPT = (
    "You are a professional anime subtitle translator. "
    "Translate the following Japanese anime dialogue lines to Brazilian Portuguese (pt-BR). "
    "Rules:\n"
    "- Preserve honorifics (senpai, kun, chan, sama, sensei) without translating them\n"
    "- Keep untranslatable terms as-is (quirk names, attack names, etc.)\n"
    "- Return ONLY a JSON array of translated strings, same length as input\n"
    "- No explanations, no markdown, just the JSON array\n"
    "- Maintain the tone and register of the original\n"
    "- Do NOT translate placeholder tokens like ⟨T0⟩ ⟨T1⟩ — keep them exactly"
)


class GeminiProvider(TranslatorProvider):
    """Gemini translation provider — higher quality contextual translation."""

    name = "gemini"

    def __init__(self, api_key: str = ""):
        self._api_key = api_key

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    async def translate_batch(
        self,
        texts: list[str],
        source_lang: str = "ja",
        target_lang: str = "pt",
    ) -> list[str]:
        if not self._api_key:
            raise ValueError("Gemini API key not configured")

        results: list[str] = []
        for i in range(0, len(texts), _BATCH_SIZE):
            chunk = texts[i : i + _BATCH_SIZE]
            translated = await self._translate_chunk(chunk)
            results.extend(translated)
            if i + _BATCH_SIZE < len(texts):
                await asyncio.sleep(0.5)
        return results

    async def _translate_chunk(self, texts: list[str]) -> list[str]:
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": (
                                f"{_SYSTEM_PROMPT}\n\n"
                                f"Input lines:\n{json.dumps(texts, ensure_ascii=False)}"
                            )
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 8192,
            },
        }
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    _API_URL,
                    params={"key": self._api_key},
                    json=payload,
                )
                resp.raise_for_status()
                content = resp.json()
                text_out = content["candidates"][0]["content"]["parts"][0]["text"]
                text_out = text_out.strip()
                if text_out.startswith("```"):
                    text_out = text_out.split("```")[1]
                    if text_out.startswith("json"):
                        text_out = text_out[4:]
                translated = json.loads(text_out)
                if isinstance(translated, list) and len(translated) == len(texts):
                    return translated
                print(f"[Gemini] Unexpected response length: {len(translated)} vs {len(texts)}")
                return texts
        except Exception as e:
            print(f"[Gemini] translate erro: {e}")
            return texts
