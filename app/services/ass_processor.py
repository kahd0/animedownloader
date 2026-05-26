from __future__ import annotations
import re

_TAG_RE = re.compile(r"\{[^}]*\}")
_NEWLINE_RE = re.compile(r"\\[Nnh]")
_PLACEHOLDER_FMT = "⟨T{}⟩"  # ⟨T0⟩, ⟨T1⟩, ...
_PLACEHOLDER_RE = re.compile(r"⟨T\d+⟩")


def load(path: str):
    """Load an ASS/SSA/SRT file. Returns pysubs2.SSAFile."""
    import pysubs2
    return pysubs2.load(path)


def save(subs, path: str, encoding: str = "utf-8-sig") -> None:
    """Save subtitle file."""
    subs.save(path, encoding=encoding)


def extract_dialogue_texts(subs) -> list[str]:
    """Return the plain text of every Dialogue line (tags stripped)."""
    texts = []
    for line in subs:
        if line.type == "Dialogue":
            texts.append(line.plaintext)
    return texts


def apply_translated_texts(subs, texts: list[str]):
    """Apply translated text back to Dialogue lines, preserving structure."""
    idx = 0
    for line in subs:
        if line.type == "Dialogue":
            if idx < len(texts):
                # Replace text while keeping all tags intact
                original_text = line.text
                translated_plain = texts[idx]
                line.text = _merge_tags_with_translation(original_text, translated_plain)
                idx += 1
    return subs


def protect_tags(text: str) -> tuple[str, list[str]]:
    """Replace ASS inline tags and special sequences with placeholders.
    Returns (protected_text, token_list).
    """
    tokens: list[str] = []

    def _replace(m: re.Match) -> str:
        token = _PLACEHOLDER_FMT.format(len(tokens))
        tokens.append(m.group(0))
        return token

    protected = _TAG_RE.sub(_replace, text)
    protected = _NEWLINE_RE.sub(
        lambda m: _replace(m),  # type: ignore[arg-type]
        protected,
    )
    # Fix: re-apply newline replacement properly
    # Re-do: combine both into one pass
    return protected, tokens


def restore_tags(text: str, tokens: list[str]) -> str:
    """Restore tag placeholders back to original tags."""
    def _restore(m: re.Match) -> str:
        idx = int(m.group(0)[2:-1])  # ⟨T3⟩ → 3
        return tokens[idx] if idx < len(tokens) else m.group(0)

    return _PLACEHOLDER_RE.sub(_restore, text)


def _merge_tags_with_translation(original_text: str, translated_plain: str) -> str:
    """Keep leading/trailing tags from original, insert translated text in middle."""
    # Extract leading tags
    leading = ""
    m_lead = re.match(r"^(\{[^}]*\})+", original_text)
    if m_lead:
        leading = m_lead.group(0)

    # Extract trailing tags
    trailing = ""
    m_trail = re.search(r"(\{[^}]*\})+$", original_text)
    if m_trail:
        trailing = m_trail.group(0)

    # Replace soft line breaks with ASS \N
    body = translated_plain.replace("\n", "\\N")
    return f"{leading}{body}{trailing}"


def has_ass_content(path: str) -> bool:
    """Returns True if the file appears to be an ASS/SSA subtitle."""
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            header = f.read(512)
        return "[Script Info]" in header or "[V4+ Styles]" in header
    except Exception:
        return False
