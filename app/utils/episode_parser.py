import re

_SXEX = re.compile(r'[Ss]\d+[Ee](\d+)')
_EPNUM = re.compile(r'(?:[\s\-])0?(\d+)(?:\D|$)')

def extract_episode_number(text: str) -> int | None:
    m = _SXEX.search(text) or _EPNUM.search(text)
    return int(m.group(1)) if m else None
