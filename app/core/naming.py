import re
import os

def smart_rename(filename):
    """[SubsPlease] Show - 12 (1080p) [hash].mkv  →  Show - S01E12.mkv"""
    m = re.match(r'\[SubsPlease\]\s+(.+?)\s+-\s+(\d+)\s+\(\d+p\)', filename, re.I)
    if not m:
        return filename
    show = m.group(1).strip()
    ep = int(m.group(2))
    ext = os.path.splitext(filename)[1]
    season = 1
    s_match = re.search(
        r'(?:[-–]\s*)?(?:(\d+)(?:st|nd|rd|th)\s+season|season\s+(\d+)|(?<!\w)[Ss](\d+)$)',
        show, re.I
    )
    if s_match:
        season = int(next(g for g in s_match.groups() if g))
        show = re.sub(
            r'\s*(?:[-–]\s*)?(?:\d+(?:st|nd|rd|th)\s+season|season\s+\d+|(?<!\w)[Ss]\d+)$',
            '', show, flags=re.I
        ).strip()
    return f"{show} - S{season:02d}E{ep:02d}{ext}"

def _strip_season(s: str) -> str:
    return re.sub(
        r'\s*(?:s\d+|season\s*\d+|part\s*\d+|\d+(?:st|nd|rd|th)\s*season)$',
        '', s, flags=re.IGNORECASE,
    ).strip()


def matches_pattern(text_to_check: str, pattern: str) -> bool:
    """
    Verifica se um nome de arquivo/show corresponde a um padrão monitorado.
    Para arquivos SubsPlease, compara apenas o título extraído (não o nome completo)
    para evitar falsos positivos como "Naruto" batendo em "Boruto - Naruto Next Generations".
    """
    pl = _strip_season(pattern.lower())
    sl = text_to_check.lower()

    # Para arquivos SubsPlease, extrai só o título do show para comparação precisa
    sp_match = re.match(r'\[subsplease\]\s+(.+?)\s+-\s+\d+\b', sl)
    if sp_match:
        candidate = _strip_season(sp_match.group(1).strip())
        if candidate == pl:
            return True
        # Padrão é prefixo do título (ex: "Boruto" bate em "Boruto - Naruto Next Generations")
        if candidate.startswith(pl):
            return True
        # Sobreposição: TODOS os termos do padrão devem estar no candidato (mínimo 2)
        def _words(t): return set(re.findall(r'[a-z]{4,}', t))
        pw, cw = _words(pl), _words(candidate)
        if len(pw) >= 2 and pw.issubset(cw):
            return True
        return False

    # Fallback para arquivos fora do formato SubsPlease
    sl_norm = _strip_season(sl)
    if pl == sl_norm or sl_norm.startswith(pl):
        return True
    def _words(t): return set(re.findall(r'[a-z]{4,}', t))
    pw, sw = _words(pl), _words(sl_norm)
    if len(pw) >= 2 and pw.issubset(sw):
        return True

    return False
