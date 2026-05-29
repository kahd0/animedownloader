"""Tradução de legendas (.ass) para PT-BR via TranslationService."""
from __future__ import annotations
import asyncio
import os
import shutil
import subprocess


async def _extract_source_ass(video_path: str, tmp_path: str) -> tuple[str | None, bool]:
    """Obtém o .ass de origem: usa externo se existir, senão extrai do vídeo via ffmpeg."""
    base = os.path.splitext(video_path)[0]
    for ext in (".ass", ".ssa"):
        if os.path.exists(base + ext):
            return base + ext, False
    if os.path.exists(base + ".srt"):
        proc = await asyncio.to_thread(
            subprocess.run,
            ["ffmpeg", "-y", "-i", base + ".srt", "-c:s", "ass", tmp_path],
            capture_output=True, text=True,
        )
        if proc.returncode == 0 and os.path.exists(tmp_path):
            return tmp_path, True
        return None, False

    proc = await asyncio.to_thread(
        subprocess.run,
        ["ffmpeg", "-y", "-i", video_path, "-map", "0:s:0", "-c:s", "ass", tmp_path],
        capture_output=True, text=True,
    )
    if proc.returncode == 0 and os.path.exists(tmp_path):
        return tmp_path, True
    return None, False


async def translate_video_subtitle(video_path: str) -> dict:
    """Traduz a legenda do vídeo para PT-BR e salva como {base}.pt.ass."""
    if not os.path.exists(video_path):
        return {"ok": False, "output_path": None, "error": f"Arquivo não encontrado: {video_path}"}

    expected_output = os.path.splitext(video_path)[0] + ".pt.ass"
    tmp_src = expected_output + ".src.tmp.ass"

    src_path, is_tmp = await _extract_source_ass(video_path, tmp_src)
    if not src_path:
        return {
            "ok": False,
            "output_path": None,
            "error": "Não foi possível obter a legenda de origem (sem .ass/.srt externo nem stream embutido)",
        }

    try:
        shutil.copy2(src_path, expected_output)

        from app.services.translation_service import TranslationService
        await TranslationService().translate(expected_output)

        return {"ok": True, "output_path": expected_output, "error": None}
    except Exception as e:
        return {"ok": False, "output_path": None, "error": str(e)}
    finally:
        if is_tmp and os.path.exists(tmp_src):
            try:
                os.remove(tmp_src)
            except Exception:
                pass
