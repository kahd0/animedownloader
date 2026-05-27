import asyncio
import httpx
import re
import os
import io
import xml.etree.ElementTree as ET
from .config import API_URL, SEARCH_URL, JIKAN_API, OPENSUBTITLES_API, get_subs_dir

async def fetch_rss_feed(feed_url: str, show_name: str = "") -> list[dict]:
    """Fetches and parses an RSS feed. Returns items in process_releases() format."""
    from ..utils.episode_parser import extract_episode_number
    url = feed_url.replace("{show}", show_name.replace(" ", "+")) if "{show}" in feed_url else feed_url
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=15, follow_redirects=True)
            resp.raise_for_status()
            content = resp.text
    except Exception as e:
        print(f"RSS fetch erro ({url}): {e}")
        return []
    try:
        ns_map = {}
        for event, elem in ET.iterparse(io.StringIO(content), events=["start-ns"]):
            ns_map[elem[0]] = elem[1]
        root = ET.fromstring(content)
    except ET.ParseError as e:
        print(f"RSS parse erro ({url}): {e}")
        return []
    releases = []
    for item in root.findall(".//item"):
        title_el = item.find("title")
        if title_el is None:
            continue
        title = title_el.text or ""
        ep_num = extract_episode_number(title)
        if ep_num is None:
            continue
        magnet = None
        for uri in ns_map.values():
            el = item.find(f"{{{uri}}}magnet")
            if el is not None and el.text and el.text.startswith("magnet:"):
                magnet = el.text
                break
        if not magnet:
            enc = item.find("enclosure")
            if enc is not None:
                u = enc.get("url", "")
                if u.startswith("magnet:"):
                    magnet = u
        if not magnet:
            link_el = item.find("link")
            if link_el is not None and link_el.text and link_el.text.startswith("magnet:"):
                magnet = link_el.text
        if not magnet:
            continue
        res_match = re.search(r"(\d{3,4})p", title, re.IGNORECASE)
        res = res_match.group(1) if res_match else "1080"
        releases.append({"show": title, "episode": ep_num, "downloads": [{"res": res, "magnet": magnet}]})
    return releases

async def check_for_app_updates(repo):
    """Verifica se há uma nova versão e retorna info + link do asset correto."""
    import platform
    async with httpx.AsyncClient() as client:
        try:
            url = f"https://api.github.com/repos/{repo}/releases/latest"
            resp = await client.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                version = data.get("tag_name")

                # Identificar qual arquivo baixar baseado no OS
                asset_url = None
                system = platform.system().lower()

                for asset in data.get("assets", []):
                    name = asset.get("name", "").lower()
                    if system == "windows" and name.endswith(".exe"):
                        asset_url = asset.get("browser_download_url")
                        break
                    elif system == "linux" and ("linux" in name or name.endswith(".bin") or "." not in name.split('/')[-1]):
                        # No linux geralmente o binário não tem extensão ou tem 'linux' no nome
                        if "windows" not in name:
                            asset_url = asset.get("browser_download_url")
                            break

                return {
                    "tag_name": version,
                    "html_url": data.get("html_url"),
                    "body": data.get("body"),
                    "asset_url": asset_url,
                    "file_name": data.get("assets")[0].get("name") if data.get("assets") else "update"
                }
        except Exception as e:
            print(f"Erro ao verificar atualizações: {e}")
    return None

async def fetch_latest_releases():
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(API_URL, timeout=15)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching from SubsPlease: {e}")
            return {}

async def search_anime_history(query):
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{SEARCH_URL}{query}", timeout=15)
            response.raise_for_status()
            data = response.json()
            return data.items() if isinstance(data, dict) else []
        except Exception as e:
            print(f"Error searching anime history: {e}")
            return []

async def search_anime_jikan(query: str, limit: int = 20) -> list[dict]:
    """Busca animes pelo título no Jikan (MyAnimeList). Retorna lista de dicts."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                f"{JIKAN_API}/anime",
                params={"q": query, "limit": limit, "order_by": "popularity", "sort": "asc"},
                timeout=10,
            )
            resp.raise_for_status()
            results = []
            for item in resp.json().get("data", []):
                results.append({
                    "title":         item.get("title_english") or item.get("title"),
                    "title_jp":      item.get("title"),
                    "episode_count": item.get("episodes"),
                    "cover_url":     item.get("images", {}).get("jpg", {}).get("image_url"),
                    "airing_status": item.get("status"),
                    "year":          item.get("year"),
                    "mal_id":        item.get("mal_id"),
                })
            return results
        except Exception as e:
            print(f"Erro na busca Jikan: {e}")
            return []


async def fetch_anime_metadata(title_pattern):
    """Busca título oficial, status e URL da capa no Jikan (MyAnimeList)."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                f"{JIKAN_API}/anime",
                params={"q": title_pattern, "limit": 8},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            if not data:
                return None
            # Prefer currently airing entry so S2 isn't replaced by S1's metadata
            item = next((d for d in data if d.get("status") == "Currently Airing"), data[0])
            studios = [s.get("name") for s in item.get("studios", []) if s.get("name")]
            season_raw = item.get("season") or ""
            return {
                "official_title":  item.get("title_english") or item.get("title"),
                "cover_url":       item.get("images", {}).get("jpg", {}).get("large_image_url"),
                "airing_status":   item.get("status"),
                "total_episodes":  item.get("episodes"),
                "score":           item.get("score"),
                "studio":          studios[0] if studios else None,
                "season":          season_raw.capitalize() if season_raw else None,
                "mal_year":        item.get("year"),
                "synopsis":        item.get("synopsis"),
            }
        except Exception as e:
            print(f"Erro ao buscar metadados Jikan: {e}")
            return None

def _normalize_series_name(show_name):
    """Remove indicadores de ep/temporada/resolução do nome da série."""
    name = re.sub(r'\b[Ss]\d{1,2}[Ee]\d+\b', '', show_name)
    name = re.sub(r'\b[Ss]\d{1,2}\b', '', name)
    name = re.sub(r'\b[Ee]\d+\b', '', name)
    name = re.sub(r'\b\d{3,4}p\b.*$', '', name, flags=re.I)
    name = re.sub(r'\s+-\s+.*$', '', name)
    return name.strip()

def _make_ep_regex(ep_num):
    return re.compile(rf'(?:[\s\-_]|[Ee]p?)0*{int(ep_num)}(?:\D|$)')

def _lang_from_filename(filename):
    """Infere idioma a partir do nome do arquivo de legenda."""
    f = filename.lower()
    if any(t in f for t in ('pt-br', 'ptbr', 'portuguese', 'brasil', '.por.', '_por_')):
        return 'por'
    if any(t in f for t in ('.eng.', '_eng_', 'english')):
        return 'eng'
    return None


def _title_words(text):
    """Retorna palavras significativas (4+ chars) de um texto, sem stop words."""
    _STOPS = frozenset({'that', 'this', 'with', 'from', 'they', 'will', 'have', 'been', 'were', 'after'})
    words = set(re.findall(r'[a-z]{4,}', text.lower()))
    return words - _STOPS

def _title_matches(series_name, candidate_title, release_name, threshold=0.5):
    """Verifica similaridade de título. Exige pelo menos 2 palavras em comum."""
    query_words = _title_words(series_name)
    if len(query_words) < 2:
        return True  # Título com poucas palavras distintivas — não filtra
    for source in (candidate_title, release_name):
        if not source:
            continue
        result_words = _title_words(source)
        overlap = query_words & result_words
        if len(overlap) >= 2 and len(overlap) / len(query_words) >= threshold:
            return True
    return False

async def _search_opensubtitles(series_name, ep_num, api_key):
    """Busca legendas PT-BR no OpenSubtitles (fallback). Filtra por similaridade de título."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{OPENSUBTITLES_API}/subtitles",
                params={
                    "query": series_name,
                    "episode_number": ep_num,
                    "languages": "pt-BR",
                    "type": "episode",
                },
                headers={
                    "Api-Key": api_key,
                    "Content-Type": "application/json",
                    "User-Agent": "AnimeMonitor/1.0",
                },
                timeout=15,
            )
            if resp.status_code != 200:
                print(f"OpenSubtitles HTTP {resp.status_code}: {resp.text[:200]}")
                return []
            data = resp.json().get("data", [])
    except Exception as e:
        print(f"OpenSubtitles search erro: {e}")
        return []

    subs = []
    for entry in data[:30]:
        attrs = entry.get("attributes", {})
        files = attrs.get("files", [])
        if not files:
            continue

        # Filtro de título: descarta resultados claramente de outro anime
        feature_title = attrs.get("feature_details", {}).get("title", "")
        release_name  = attrs.get("release", "")
        if not _title_matches(series_name, feature_title, release_name):
            continue

        file_info = files[0]
        lang_code = attrs.get("language", "")
        lang = "por" if lang_code in ("pt-BR", "pt") else ("eng" if lang_code == "en" else lang_code)
        codec = attrs.get("format", "srt").lower()
        subs.append({
            'source': 'opensubtitles',
            'id': 0,
            'filename': file_info.get("file_name", ""),
            'info': {
                'lang': lang,
                'desc': f"OpenSubtitles • {release_name}",
                'codec': codec,
            },
            '_dl_info': {
                'file_id': file_info.get("file_id"),
                'api_key': api_key,
            },
        })
    return subs

async def find_subtitles(show_name, ep_num):
    """Busca legendas usando as fontes configuradas na ordem de prioridade."""
    from .config import get_subtitle_sources, get_setting
    series_name = _normalize_series_name(show_name)
    ep_str = str(ep_num).zfill(2)
    all_subs = []

    for source in get_subtitle_sources():
        if not source.get("enabled"):
            continue
        if source["id"] == "opensubtitles":
            api_key = get_setting("opensubtitles_api_key", "")
            if api_key:
                subs = await _search_opensubtitles(series_name, ep_num, api_key)
                all_subs.extend(subs)

    return all_subs, series_name, ep_str

def _resolve_sub_path(series_name, ep_str, ext, target_video_path=None):
    """Retorna o path onde a legenda deve ser salva."""
    if target_video_path:
        video_dir = os.path.dirname(target_video_path)
        video_stem = os.path.splitext(os.path.basename(target_video_path))[0]
        return os.path.join(video_dir, f"{video_stem}.{ext}")
    subs_dir = get_subs_dir()
    os.makedirs(subs_dir, exist_ok=True)
    safe = re.sub(r'[^\w\s-]', '', series_name).strip().lower()
    return os.path.join(subs_dir, f"{safe}_ep{ep_str}.{ext}")

async def _download_opensubtitles_sub(sub, series_name, ep_str, target_video_path=None):
    try:
        dl_info = sub.get('_dl_info', {})
        file_id = dl_info.get('file_id')
        api_key = dl_info.get('api_key')
        if not file_id or not api_key:
            return None
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{OPENSUBTITLES_API}/download",
                json={"file_id": file_id},
                headers={
                    "Api-Key": api_key,
                    "Content-Type": "application/json",
                    "User-Agent": "AnimeMonitor/1.0",
                },
                timeout=15,
            )
            resp.raise_for_status()
            link = resp.json().get("link")
            if not link:
                return None
            resp2 = await client.get(link, timeout=30)
            resp2.raise_for_status()
            content = resp2.content
        ext = sub['info'].get('codec', 'srt').lower()
        filename = _resolve_sub_path(series_name, ep_str, ext, target_video_path)
        with open(filename, 'wb') as f:
            f.write(content)
        return filename
    except Exception as e:
        print(f"Erro download OpenSubtitles: {e}")
        return None

async def download_chosen_subtitle(sub, series_name, ep_str, target_video_path=None):
    """Baixa e salva uma legenda. Despacha para o provedor correto.
    Se target_video_path for informado, salva ao lado do vídeo (substituindo legenda existente).
    Caso contrário, salva na pasta temporária de legendas."""
    if sub.get('source') == 'opensubtitles':
        return await _download_opensubtitles_sub(sub, series_name, ep_str, target_video_path)
    return None
