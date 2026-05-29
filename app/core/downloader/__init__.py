"""Pacote downloader: lógica de negócio de downloads, legendas e organização.

Mantém a API pública anterior (``from app.core.downloader import X``) reexportando
as funções a partir dos submódulos especializados.
"""
from app.core.downloader.system import open_path, trigger_magnet
from app.core.downloader.covers import download_cover
from app.core.downloader.subtitles import (
    download_subtitle,
    force_download_subs,
    get_subtitle_candidates,
    get_subtitle_candidates_for_anime,
    check_subtitle_status,
)
from app.core.downloader.translation import translate_video_subtitle
from app.core.downloader.organizer import organize_downloads
from app.core.downloader.releases import (
    search_subsplease_shows,
    process_releases,
    check_for_updates,
    check_for_updates_single,
)
from app.core.downloader.metadata import (
    refresh_single_metadata,
    refresh_all_metadata,
)

__all__ = [
    "open_path",
    "trigger_magnet",
    "download_cover",
    "download_subtitle",
    "force_download_subs",
    "get_subtitle_candidates",
    "get_subtitle_candidates_for_anime",
    "check_subtitle_status",
    "translate_video_subtitle",
    "organize_downloads",
    "search_subsplease_shows",
    "process_releases",
    "check_for_updates",
    "check_for_updates_single",
    "refresh_single_metadata",
    "refresh_all_metadata",
]
