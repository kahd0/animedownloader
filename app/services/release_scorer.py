from __future__ import annotations
import re

from app.models.release import Release
from app.models.subtitle import SubtitleResult
from app.services.release_normalizer import is_hevc, is_dual_audio


def score_release(release: Release, preferred_group: str | None = None) -> int:
    """Compute quality score for a release. Higher = better."""
    score = 0

    if release.language == "pt-br":
        score += 100

    res_num = int(release.resolution.rstrip("p")) if release.resolution.rstrip("p").isdigit() else 1080
    if res_num >= 1080:
        score += 40
    elif res_num >= 720:
        score += 20

    if release.source in ("SubsPlease", "Erai-raws"):
        score += 30

    if preferred_group and release.release_group == preferred_group:
        score += 50

    if is_hevc(release.title):
        score -= 20

    if is_dual_audio(release.title):
        score -= 30

    return score


def score_subtitle(result: SubtitleResult) -> int:
    """Compute quality score for a subtitle result. Higher = better."""
    score = 0

    if result.is_portuguese:
        score += 100

    if result.format == "ass":
        score += 80
    elif result.format == "srt":
        score += 40

    if result.provider == "opensubtitles":
        score += 30

    if result.provider == "animetosho":
        score += 20

    return score


def rank_releases(releases: list[Release], preferred_group: str | None = None) -> list[Release]:
    """Return releases sorted by score descending, computing scores in-place."""
    for r in releases:
        r.score = score_release(r, preferred_group)
    return sorted(releases, key=lambda r: r.score, reverse=True)


def rank_subtitles(results: list[SubtitleResult]) -> list[SubtitleResult]:
    """Return subtitles sorted by score descending, computing scores in-place."""
    for r in results:
        r.score = score_subtitle(r)
    return sorted(results, key=lambda r: r.score, reverse=True)
