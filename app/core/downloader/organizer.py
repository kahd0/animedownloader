"""Organização de downloads: move vídeos para a pasta final e pareia legendas."""
import asyncio
import os
import re
import shutil

from app.core.config import get_source_dir, get_final_dir, get_subs_dir
from app.core.naming import smart_rename, matches_pattern
from app.core.database import get_monitored_animes, mark_episode_ready
from app.utils.episode_parser import extract_episode_number


async def organize_downloads():
    """Move vídeos e busca legendas correspondentes"""
    source_dir = get_source_dir()
    final_dir = get_final_dir()
    await asyncio.to_thread(os.makedirs, final_dir, exist_ok=True)
    moved_files = []

    # 1. Mover vídeos da pasta de Downloads para a pasta FINAL
    monitored = await get_monitored_animes()
    if os.path.exists(source_dir):

        def _get_files():
            files = []
            final_abs = os.path.abspath(final_dir)
            for root, _, fs in os.walk(source_dir):
                root_abs = os.path.abspath(root)
                # Evita recursão na pasta final se ela estiver dentro de source_dir
                if root_abs == final_abs or root_abs.startswith(final_abs + os.sep):
                    continue
                for f in fs:
                    files.append((f, os.path.join(root, f)))
            return files

        source_files = await asyncio.to_thread(_get_files)

        for filename, old_path in source_files:
            if filename.endswith((".!qB", ".part")): continue
            if not filename.lower().endswith((".mkv", ".mp4", ".avi")): continue

            for row in monitored:
                pattern = row[1]
                if matches_pattern(filename, pattern):
                    new_name = smart_rename(filename)
                    new_path = os.path.join(final_dir, new_name)
                    try:
                        await asyncio.to_thread(shutil.move, old_path, new_path)
                        if new_name != filename:
                            moved_files.append(f"Renomeado: {filename} → {new_name}")
                        else:
                            moved_files.append(f"Vídeo: {filename}")

                        # Mark episode as ready on disk (update last_ready in DB)
                        ep_num = extract_episode_number(new_name)
                        if ep_num is not None:
                            await mark_episode_ready(pattern, ep_num)

                        # Limpa pasta de origem se ficou vazia e não é a pasta raiz
                        old_dir = os.path.dirname(old_path)
                        if os.path.abspath(old_dir) != os.path.abspath(source_dir):
                            if not os.listdir(old_dir):
                                os.rmdir(old_dir)
                    except Exception as e:
                        print(f"Erro ao mover vídeo {filename}: {e}")
                    break

    # 2. Parear legendas com vídeos na pasta FINAL
    subs_dir = get_subs_dir()
    if os.path.exists(subs_dir):
        final_files = await asyncio.to_thread(os.listdir, final_dir)
        subs_files = await asyncio.to_thread(os.listdir, subs_dir)
        final_set = set(final_files)

        for video_file in final_files:
            if not video_file.lower().endswith((".mkv", ".mp4", ".avi")): continue

            ep_num = extract_episode_number(video_file)
            if ep_num is None: continue
            ep_num_str = str(ep_num).zfill(2)

            video_name_no_ext = os.path.splitext(video_file)[0]
            has_sub = any(
                f.startswith(video_name_no_ext) and f.lower().endswith((".ass", ".srt"))
                for f in final_set
            )
            if has_sub: continue

            # Derive the expected subtitle prefix from the monitored pattern
            video_safe_prefix = None
            for _, pattern, *_ in monitored:
                if matches_pattern(video_file, pattern):
                    sname = re.sub(r's\d+|e\d+|-.*$|\d+p.*$', '', pattern, flags=re.I).strip()
                    video_safe_prefix = re.sub(r'[^\w\s-]', '', sname).strip().lower()
                    break

            for sub_file in subs_files:
                sub_lower = sub_file.lower().replace("_", " ")
                if f" ep{ep_num_str}" not in sub_lower:
                    continue
                if video_safe_prefix and not sub_lower.startswith(video_safe_prefix):
                    continue
                sub_ext = os.path.splitext(sub_file)[1]
                old_sub_path = os.path.join(subs_dir, sub_file)
                new_sub_name = f"{video_name_no_ext}{sub_ext}"
                new_sub_path = os.path.join(final_dir, new_sub_name)
                try:
                    await asyncio.to_thread(shutil.move, old_sub_path, new_sub_path)
                    final_set.add(new_sub_name)
                    moved_files.append(f"Legenda pareada: {video_file}")
                except Exception as e:
                    print(f"Erro ao mover legenda {sub_file}: {e}")
                break

    return moved_files
