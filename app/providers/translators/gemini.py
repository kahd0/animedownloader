from __future__ import annotations
import asyncio
import json
import re
import time

import httpx

from app.providers.base import TranslatorProvider

_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
_BATCH_SIZE = 100
# How long to stay in fallback mode after a 429 (seconds). Shared across all instances.
_RATE_LIMIT_COOLDOWN = 120
_SYSTEM_PROMPT = (
    "You are a professional anime subtitle translator. "
    "Translate the following Japanese anime dialogue lines to Brazilian Portuguese (pt-BR). "
    "Rules:\n"
    "- Preserve honorifics (senpai, kun, chan, sama, sensei) without translating them\n"
    "- Keep untranslatable terms as-is (quirk names, attack names, etc.)\n"
    "- Return ONLY a JSON array of translated strings, same length as input\n"
    "- No explanations, no markdown, just the JSON array\n"
    "- Maintain the tone and register of the original\n"
    "- Do NOT translate placeholder tokens like ⟨T0⟩ ⟨T1⟩ or glossary markers like ⟪G0⟫ ⟪G1⟫ — keep them exactly as-is"
)


class GeminiProvider(TranslatorProvider):
    """Gemini translation provider — higher quality contextual translation."""

    name = "gemini"
    # Class-level: timestamp until which Gemini should be skipped due to rate limit.
    # Shared across all instances so a 429 in one job protects subsequent jobs too.
    _rate_limited_until: float = 0.0

    def __init__(self, api_key: str = ""):
        self._api_key = api_key

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    @classmethod
    def _is_rate_limited(cls) -> bool:
        return time.monotonic() < cls._rate_limited_until

    @classmethod
    def _set_rate_limited(cls) -> None:
        cls._rate_limited_until = time.monotonic() + _RATE_LIMIT_COOLDOWN
        print(f"[Gemini] Rate limit ativo. Usando Google Translate por {_RATE_LIMIT_COOLDOWN}s.")

    async def translate_batch(
        self,
        texts: list[str],
        source_lang: str = "ja",
        target_lang: str = "pt",
    ) -> list[str]:
        if not self._api_key:
            raise ValueError("Gemini API key not configured")

        if self._is_rate_limited():
            print("[Gemini] Rate limit ativo — usando Google Translate.")
            return await self._fallback(texts, source_lang, target_lang)

        results: list[str] = []

        for i in range(0, len(texts), _BATCH_SIZE):
            chunk = texts[i : i + _BATCH_SIZE]
            try:
                translated = await self._translate_chunk(chunk)
                results.extend(translated)
                if i + _BATCH_SIZE < len(texts):
                    await asyncio.sleep(4.5)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    print("[Gemini] Rate limit (429) — alternando legenda completa para Google Translate.")
                    self._set_rate_limited()
                    remaining = texts[i:]
                    fallback_result = await self._fallback(remaining, source_lang, target_lang)
                    results.extend(fallback_result)
                    return results
                else:
                    print(f"[Gemini] Erro HTTP: {e}")
                    remaining = texts[i:]
                    results.extend(await self._fallback(remaining, source_lang, target_lang))
                    return results
            except Exception as e:
                print(f"[Gemini] Erro de tradução: {e}")
                remaining = texts[i:]
                results.extend(await self._fallback(remaining, source_lang, target_lang))
                return results

        return results

    async def _fallback(self, texts: list[str], source_lang: str, target_lang: str) -> list[str]:
        try:
            from app.providers.translators.google import GoogleTranslateProvider
            return await GoogleTranslateProvider().translate_batch(texts, source_lang, target_lang)
        except Exception as e:
            print(f"[Gemini Fallback] Erro: {e}")
            return texts

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
                text_out = re.sub(r'^```[a-zA-Z]*\s*', '', text_out)
                text_out = re.sub(r'\s*```$', '', text_out)
            translated = json.loads(text_out)
            if isinstance(translated, list) and len(translated) == len(texts):
                return translated
            raise ValueError(f"Tamanho de resposta inesperado: {len(translated)} vs {len(texts)}")
