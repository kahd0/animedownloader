"""Tradução de legendas (.ass) para PT-BR via Gemini com fallback no Google Translate."""
import asyncio
import os
import re
import subprocess

import httpx

_ASS_TAG_RE = re.compile(r'\{[^}]*\}')
_ASS_NEWLINE_RE = re.compile(r'\\[Nnh]')
_GTRANSLATE_URL = "https://translate.googleapis.com/translate_a/single"


async def _extract_source_ass(video_path, tmp_path):
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


def _protect_ass_text(text):
    """Substitui tags ASS e quebras de linha por placeholders preservados na tradução."""
    tokens = []
    def _save(m):
        tokens.append(m.group(0))
        return f"[[[{len(tokens) - 1}]]]"
    protected = _ASS_TAG_RE.sub(_save, text)
    protected = _ASS_NEWLINE_RE.sub(_save, protected)
    return protected, tokens


def _restore_ass_text(text, tokens):
    for i, t in enumerate(tokens):
        text = text.replace(f"[[[{i}]]]", t)
    return text


async def _translate_one(client, sem, text):
    if not text.strip():
        return text
    async with sem:
        params = {
            "client": "gtx",
            "sl": "auto",
            "tl": "pt",
            "dt": "t",
            "q": text,
        }
        for attempt in range(3):
            try:
                resp = await client.get(_GTRANSLATE_URL, params=params, timeout=20.0)
                if resp.status_code == 200:
                    data = resp.json()
                    chunks = data[0] or []
                    return "".join(c[0] for c in chunks if c and c[0])
                if resp.status_code == 429:
                    await asyncio.sleep(2 + attempt * 2)
                    continue
                return text
            except Exception:
                await asyncio.sleep(1 + attempt)
        return text


async def translate_video_subtitle(video_path):
    """Traduz a legenda do vídeo para PT-BR de forma controlada."""
    if not os.path.exists(video_path):
        return {"ok": False, "output_path": None, "error": f"Arquivo não encontrado: {video_path}"}

    from app.core.config import get_gemini_api_key
    gemini_key = get_gemini_api_key()

    expected_output = os.path.splitext(video_path)[0] + ".pt.ass"
    tmp_src = expected_output + ".src.tmp.ass"

    src_path, is_tmp = await _extract_source_ass(video_path, tmp_src)
    if not src_path:
        return {"ok": False, "output_path": None, "error": "Não foi possível obter a legenda de origem (sem .ass/.srt externo nem stream embutido)"}

    try:
        raw = await asyncio.to_thread(_read_text_with_fallback, src_path)
    except Exception as e:
        if is_tmp and os.path.exists(tmp_src):
            try: os.remove(tmp_src)
            except Exception: pass
        return {"ok": False, "output_path": None, "error": f"Falha ao ler legenda de origem: {e}"}

    lines = raw.splitlines()
    dialogue_indices = []
    texts_to_translate = []
    token_sets = []

    for idx, line in enumerate(lines):
        if not line.startswith("Dialogue:"):
            continue
        parts = line.split(",", 9)
        if len(parts) < 10:
            continue
        protected, tokens = _protect_ass_text(parts[9])
        dialogue_indices.append((idx, parts))
        texts_to_translate.append(protected)
        token_sets.append(tokens)

    if not texts_to_translate:
        if is_tmp and os.path.exists(tmp_src):
            try: os.remove(tmp_src)
            except Exception: pass
        return {"ok": False, "output_path": None, "error": "Nenhuma linha de diálogo encontrada na legenda"}

    if gemini_key:
        from app.providers.translators.gemini import GeminiProvider
        provider = GeminiProvider(api_key=gemini_key)

        translated = []
        chunk_size = 30
        for i in range(0, len(texts_to_translate), chunk_size):
            chunk = texts_to_translate[i:i + chunk_size]
            success = False
            for attempt in range(4):
                try:
                    chunk_trans = await provider.translate_batch(chunk)
                    if (chunk_trans == chunk and any(re.search('[a-zA-Z]', c) for c in chunk)) or not chunk_trans:
                        if attempt < 3:
                            await asyncio.sleep(15 + attempt * 10)
                            continue
                        break
                    translated.extend(chunk_trans)
                    success = True
                    break
                except Exception:
                    if attempt < 3: await asyncio.sleep(15 + attempt * 10)
                    else: break

            if not success:
                sem = asyncio.Semaphore(8)
                async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0"}) as client:
                    chunk_fallback = await asyncio.gather(*(_translate_one(client, sem, t) for t in chunk))
                    translated.extend(chunk_fallback)

            await asyncio.sleep(4.5)
    else:
        sem = asyncio.Semaphore(8)
        async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0"}) as client:
            translated = await asyncio.gather(*(_translate_one(client, sem, t) for t in texts_to_translate))

    for (idx, parts), trans_text, tokens in zip(dialogue_indices, translated, token_sets):
        parts[9] = _restore_ass_text(trans_text, tokens)
        lines[idx] = ",".join(parts)

    try:
        def _write_output():
            with open(expected_output, "w", encoding="utf-8") as _f:
                _f.write("\n".join(lines))
        await asyncio.to_thread(_write_output)
    except Exception as e:
        if is_tmp and os.path.exists(tmp_src):
            try: os.remove(tmp_src)
            except Exception: pass
        return {"ok": False, "output_path": None, "error": f"Falha ao escrever .pt.ass: {e}"}

    if is_tmp and os.path.exists(tmp_src):
        try: os.remove(tmp_src)
        except Exception: pass

    return {"ok": True, "output_path": expected_output, "error": None}


def _read_text_with_fallback(path):
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()
