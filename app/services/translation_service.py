from __future__ import annotations
import hashlib
import os

from app.core import database as db
from app.services import ass_processor

_GLOSS_PLACEHOLDER_FMT = "⟪G{}⟫"


class TranslationService:
    """Contextual batch translation with translation memory and glossary support."""

    def __init__(self):
        self._provider = None

    def _get_provider(self):
        if self._provider is None:
            self._provider = _build_provider()
        return self._provider

    async def translate(self, subtitle_path: str, anime_id: int | None = None) -> str:
        """Translate a subtitle file in-place and return the path."""
        subs = ass_processor.load(subtitle_path)
        texts = ass_processor.extract_dialogue_texts(subs)

        if not texts:
            return subtitle_path

        glossary = await db.get_glossary()
        texts = _apply_glossary_pre(texts, glossary)

        protected, token_lists = zip(*[ass_processor.protect_tags(t) for t in texts]) if texts else ([], [])
        protected = list(protected)
        token_lists = list(token_lists)

        # Translation memory lookup
        hashes = [hashlib.sha256(t.encode()).hexdigest() for t in protected]
        translated_lines: list[str | None] = []
        to_translate_indices: list[int] = []

        for i, (h, text) in enumerate(zip(hashes, protected)):
            cached = await db.get_translation(h)
            if cached is not None:
                translated_lines.append(cached)
            else:
                translated_lines.append(None)
                to_translate_indices.append(i)

        if to_translate_indices:
            missing_texts = [protected[i] for i in to_translate_indices]
            provider = self._get_provider()
            translated_missing = await provider.translate_batch(missing_texts)

            for idx, translated in zip(to_translate_indices, translated_missing):
                translated_lines[idx] = translated
                await db.save_translation(
                    hashes[idx], protected[idx], translated, provider.name
                )

        # Restore tags
        final_lines = []
        for i, (line, tokens) in enumerate(zip(translated_lines, token_lists)):
            restored = ass_processor.restore_tags(line or protected[i], tokens)
            final_lines.append(restored)

        final_lines = _apply_glossary_post(final_lines, glossary)

        ass_processor.apply_translated_texts(subs, final_lines)
        ass_processor.save(subs, subtitle_path)
        return subtitle_path


def _build_provider():
    from app.core.config import get_setting
    from app.providers.translators.gemini import GeminiProvider
    from app.providers.translators.google import GoogleTranslateProvider

    gemini_key = get_setting("gemini_api_key", "")
    if gemini_key:
        return GeminiProvider(api_key=gemini_key)
    return GoogleTranslateProvider()


def _apply_glossary_pre(texts: list[str], glossary: list[dict]) -> list[str]:
    """Replace glossary source terms with reversible placeholders before translation."""
    if not glossary:
        return texts
    # Sort longest first so multi-word terms are replaced before their substrings
    ordered = sorted(enumerate(glossary), key=lambda x: len(x[1]["source"]), reverse=True)
    result = []
    for text in texts:
        for i, entry in ordered:
            text = text.replace(entry["source"], _GLOSS_PLACEHOLDER_FMT.format(i))
        result.append(text)
    return result


def _apply_glossary_post(texts: list[str], glossary: list[dict]) -> list[str]:
    """Restore glossary placeholders to their target terms after translation."""
    if not glossary:
        return texts
    result = []
    for text in texts:
        for i, entry in enumerate(glossary):
            text = text.replace(_GLOSS_PLACEHOLDER_FMT.format(i), entry["target"])
        result.append(text)
    return result
