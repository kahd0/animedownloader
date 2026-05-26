from __future__ import annotations
import re

from app.models.release import Release
from app.utils.episode_parser import extract_episode_number

_GROUP_RE = re.compile(r"^\[([^\]]+)\]")
_RES_RE = re.compile(r"\b(\d{3,4})p\b", re.IGNORECASE)
_EP_TAG_RE = re.compile(r"\s*-\s*\d{2,3}(?:\s|$)")
_SEASON_RE = re.compile(r"\bS(\d{1,2})E\d+\b", re.IGNORECASE)
_BRACKET_RE = re.compile(r"\s*[\(\[][^\)\]]*[\)\]]")
_TRAILING_DASH_RE = re.compile(r"\s*-\s*\d+\s*$")
_CRC_RE = re.compile(r"\b[0-9A-Fa-f]{8}\b")
_HEVC_RE = re.compile(r"\b(HEVC|x265|h\.?265|AV1)\b", re.IGNORECASE)
_DUAL_RE = re.compile(r"\b(dual[\s\-]?audio|dual|dub)\b", re.IGNORECASE)


def normalize_title(raw_title: str) -> str:
    """Strip group tags, resolution, episode numbers and junk from a release title."""
    title = _GROUP_RE.sub("", raw_title).strip()
    title = _BRACKET_RE.sub("", title).strip()
    title = _RES_RE.sub("", title).strip()
    title = _EP_TAG_RE.sub("", title).strip()
    title = _TRAILING_DASH_RE.sub("", title).strip()
    title = _CRC_RE.sub("", title).strip()
    return title


def detect_resolution(text: str) -> str:
    m = _RES_RE.search(text)
    return f"{m.group(1)}p" if m else "1080p"


def detect_release_group(text: str) -> str | None:
    m = _GROUP_RE.match(text)
    return m.group(1) if m else None


def detect_season(text: str) -> int:
    m = _SEASON_RE.search(text)
    return int(m.group(1)) if m else 1


def is_hevc(text: str) -> bool:
    return bool(_HEVC_RE.search(text))


def is_dual_audio(text: str) -> bool:
    return bool(_DUAL_RE.search(text))


def normalize_release(
    title: str,
    magnet: str,
    source: str,
    episode: int | None = None,
) -> Release:
    """Build a normalized Release object from a raw title + magnet."""
    if episode is None:
        episode = extract_episode_number(title)

    torrent_hash: str | None = None
    for part in magnet.split("&"):
        if part.startswith("xt=urn:btih:"):
            torrent_hash = part.split(":")[-1].lower()
            break

    return Release(
        title=title,
        normalized_title=normalize_title(title),
        episode=episode,
        season=detect_season(title),
        resolution=detect_resolution(title),
        source=source,
        magnet=magnet,
        torrent_hash=torrent_hash,
        release_group=detect_release_group(title),
    )


def fuzzy_match_title(query: str, candidate: str, threshold: float = 0.6) -> bool:
    """Returns True if candidate fuzzy-matches query at or above threshold."""
    try:
        from rapidfuzz import fuzz
        score = fuzz.token_set_ratio(query.lower(), candidate.lower())
        return score >= threshold * 100
    except ImportError:
        # Fallback: word overlap
        q_words = set(re.findall(r"\w{3,}", query.lower()))
        c_words = set(re.findall(r"\w{3,}", candidate.lower()))
        if not q_words:
            return True
        overlap = q_words & c_words
        return len(overlap) / len(q_words) >= threshold
