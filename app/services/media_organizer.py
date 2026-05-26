from __future__ import annotations
import os
import re
import shutil
from pathlib import Path

_VIDEO_EXTS = {".mkv", ".mp4", ".avi", ".mov", ".m4v"}
_SUB_EXTS = {".ass", ".srt", ".sub", ".ssa"}
_INVALID_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_DEFAULT_PATTERN = "{title} - S{season:02d}E{episode:02d}"


class MediaOrganizer:
    """Rename and move video+subtitle files into the final directory."""

    def __init__(self, naming_pattern: str = _DEFAULT_PATTERN):
        self._pattern = naming_pattern

    def build_filename(self, title: str, episode: int, season: int = 1, ext: str = ".mkv") -> str:
        name = self._pattern.format(title=title, episode=episode, season=season)
        name = _sanitize(name)
        return f"{name}{ext}"

    async def organize(
        self,
        title: str,
        episode: int,
        source_dir: str,
        dest_dir: str,
        season: int = 1,
    ) -> str | None:
        """Find video in source_dir matching episode, move to dest_dir, pair subtitles."""
        video_path = _find_video(source_dir, title, episode)
        if not video_path:
            return None

        os.makedirs(dest_dir, exist_ok=True)
        ext = Path(video_path).suffix
        dest_name = self.build_filename(title, episode, season, ext)
        dest_path = os.path.join(dest_dir, dest_name)

        if os.path.abspath(video_path) != os.path.abspath(dest_path):
            shutil.move(video_path, dest_path)

        # Move subtitle alongside video
        sub_path = _find_subtitle(source_dir, video_path)
        if sub_path:
            sub_ext = Path(sub_path).suffix
            sub_dest = os.path.splitext(dest_path)[0] + sub_ext
            shutil.move(sub_path, sub_dest)

        return dest_path


def _find_video(directory: str, title: str, episode: int) -> str | None:
    """Find video file matching title+episode in directory."""
    if not os.path.isdir(directory):
        return None

    from app.utils.episode_parser import extract_episode_number

    title_words = set(re.findall(r"\w{3,}", title.lower()))
    best: str | None = None

    for fname in os.listdir(directory):
        if Path(fname).suffix.lower() not in _VIDEO_EXTS:
            continue
        full = os.path.join(directory, fname)
        ep = extract_episode_number(fname)
        if ep != episode:
            continue
        # Check title overlap
        fname_words = set(re.findall(r"\w{3,}", fname.lower()))
        overlap = title_words & fname_words
        if len(overlap) >= max(1, len(title_words) // 2):
            best = full
            break

    return best


def _find_subtitle(directory: str, video_path: str) -> str | None:
    """Find subtitle file next to or near a video file."""
    stem = os.path.splitext(os.path.basename(video_path))[0]
    for ext in _SUB_EXTS:
        candidate = os.path.join(directory, f"{stem}{ext}")
        if os.path.exists(candidate):
            return candidate
    # Fallback: any subtitle in directory
    for fname in os.listdir(directory):
        if Path(fname).suffix.lower() in _SUB_EXTS:
            return os.path.join(directory, fname)
    return None


def _sanitize(name: str) -> str:
    name = _INVALID_CHARS_RE.sub("", name)
    return name.strip(". ")
