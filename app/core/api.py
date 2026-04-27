import httpx
import re
import lzma
import os
from .config import API_URL, SEARCH_URL, ANIMETOSHO_API, JIKAN_API, get_subs_dir

async def check_for_app_updates(repo):
    """Verifica se há uma nova versão no GitHub releases."""
    async with httpx.AsyncClient() as client:
        try:
            url = f"https://api.github.com/repos/{repo}/releases/latest"
            resp = await client.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "tag_name": data.get("tag_name"),
                    "html_url": data.get("html_url"),
                    "body": data.get("body")
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
            return {
                "official_title": item.get("title_english") or item.get("title"),
                "cover_url": item.get("images", {}).get("jpg", {}).get("large_image_url"),
                "airing_status": item.get("status"),
            }
        except Exception as e:
            print(f"Erro ao buscar metadados Jikan: {e}")
            return None

async def find_subtitles(show_name, ep_num):
    """Busca candidatos no AnimeTosho sem baixar. Retorna (subs, series_name, ep_str)."""
    series_name = re.sub(rf's\d+|e\d+|-.*$|\d+p.*$', '', show_name, flags=re.I).strip()
    ep_str = str(ep_num).zfill(2)
    queries = [f'{series_name} {ep_str}', f'{series_name} Brazilian', f'{series_name} Multi']
    all_subs, seen_ids = [], set()

    async with httpx.AsyncClient() as client:
        for q in queries:
            try:
                resp = await client.get(ANIMETOSHO_API, params={"q": q}, timeout=10)
                data = resp.json()
                if not data or not isinstance(data, list):
                    continue
                
                for entry in data[:10]:
                    if not entry or not re.search(rf'(\s|-|[Ee])0?{int(ep_num)}(\D|$)', entry.get('title', '')):
                        continue

                    det_resp = await client.get(ANIMETOSHO_API, params={"show": "torrent", "id": entry['id']})
                    det_data = det_resp.json()
                    if not det_data or not isinstance(det_data, dict):
                        continue

                    for f in det_data.get('files', []):
                        if not f or not re.search(rf'(\s|-|[Ee])0?{int(ep_num)}(\D|$)', f.get('filename', '')):
                            continue
                        for a in f.get('attachments', []):
                            if a.get('type') == 'subtitle' and a.get('id') and a['id'] not in seen_ids:
                                all_subs.append(a)
                                seen_ids.add(a['id'])
            except Exception as e:
                print(f"Erro busca legenda ({q}): {e}")
                continue

    return all_subs, series_name, ep_str

async def download_chosen_subtitle(sub, series_name, ep_str):
    """Baixa e salva uma legenda específica. Retorna path ou None."""
    try:
        dl_url = f"https://storage.animetosho.org/attach/{sub['id']:08x}/file.xz"
        async with httpx.AsyncClient() as client:
            resp = await client.get(dl_url, timeout=15)
            resp.raise_for_status()
            data = lzma.decompress(resp.content)
        ext = sub['info'].get('codec', 'ass').lower()
        subs_dir = get_subs_dir()
        os.makedirs(subs_dir, exist_ok=True)
        safe = re.sub(r'[^\w\s-]', '', series_name).strip().lower()
        filename = os.path.join(subs_dir, f"{safe}_ep{ep_str}.{ext}")
        with open(filename, 'wb') as f:
            f.write(data)
        return filename
    except Exception as e:
        print(f"Erro download/salvar legenda: {e}")
        return None
