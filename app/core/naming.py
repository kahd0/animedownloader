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

def matches_pattern(filename, pattern):
    """Verifica se o arquivo corresponde ao padrão do anime, ignorando sufixos de temporada."""
    fl = filename.lower()
    pl = pattern.lower()

    if pl in fl:
        return True

    # Remove marcadores de temporada ("Show S2" → "Show")
    stripped = re.sub(
        r'\s*(?:[-–]\s*)?(?:\d+(?:st|nd|rd|th)\s+season|season\s+\d+|(?<!\w)s\d+)$',
        '', pl
    ).strip()
    
    if stripped and stripped != pl and stripped in fl:
        return True
    
    return False
