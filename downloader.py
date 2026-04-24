import httpx
import re
import webbrowser
import platform
import subprocess
import os
from database import get_monitored_animes, update_last_episode

API_URL = "https://subsplease.org/api/?f=latest&tz=UTC"
SEARCH_URL = "https://subsplease.org/api/?f=search&tz=UTC&s="

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
            # Search API returns a dict of releases
            return data.items() if isinstance(data, dict) else []
        except Exception as e:
            print(f"Error searching anime history: {e}")
            return []

def trigger_magnet(magnet_link):
    try:
        if platform.system() == "Windows":
            os.startfile(magnet_link)
        elif platform.system() == "Darwin":
            subprocess.run(["open", magnet_link])
        else:
            subprocess.run(["xdg-open", magnet_link])
        return True
    except Exception as e:
        print(f"Error opening magnet link: {e}")
        # Fallback to webbrowser
        return webbrowser.open(magnet_link)

async def process_releases(releases_list, monitored_list=None):
    """
    releases_list: list of dicts (from search) or items from latest.items()
    """
    if monitored_list is None:
        monitored_list = await get_monitored_animes()
    
    if not monitored_list:
        return []

    downloads_triggered = []
    
    # Normalize releases to a consistent format
    normalized = []
    for item in releases_list:
        if isinstance(item, tuple): # From latest.items()
            info = item[1]
        else: # From search API
            info = item
        normalized.append(info)

    # Sort by episode
    normalized.sort(key=lambda x: int(x.get('episode', 0)) if str(x.get('episode', '')).isdigit() else 0)

    for info in normalized:
        show_name = info.get('show', '')
        try:
            episode_num = int(info.get('episode', 0))
        except (ValueError, TypeError):
            continue

        for anime_id, pattern, last_ep, res in monitored_list:
            if pattern.lower() in show_name.lower():
                if episode_num > last_ep:
                    magnet = None
                    for dl in info.get('downloads', []):
                        if dl.get('res') == res.replace('p', ''):
                            magnet = dl.get('magnet')
                            break
                    
                    if not magnet and info.get('downloads'):
                        magnet = info['downloads'][0].get('magnet')

                    if magnet:
                        if trigger_magnet(magnet):
                            await update_last_episode(pattern, episode_num)
                            downloads_triggered.append(f"{show_name} - {episode_num} ({res})")
                            # Update the local last_ep for the next release in the same loop
                            # (Important if multiple episodes are found for the same anime)
                            monitored_list = [
                                (aid, p, episode_num if p == pattern else lep, r)
                                for aid, p, lep, r in monitored_list
                            ]
    
    return downloads_triggered

async def check_for_updates():
    monitored = await get_monitored_animes()
    if not monitored:
        return []

    # 1. Tenta o feed global (rápido)
    latest = await fetch_latest_releases()
    triggered = await process_releases(latest.items(), monitored)
    
    # 2. Se algum anime monitorado ainda puder ter episódios novos (busca profunda individual)
    # Fazemos isso para garantir que episódios que saíram do feed "latest" sejam pegos
    all_triggered = list(triggered)
    
    # Pegamos a lista atualizada (com os eps que acabamos de baixar, se houver)
    monitored = await get_monitored_animes()
    
    for _, pattern, _, _ in monitored:
        # Se esse anime não foi atualizado no passo 1, fazemos uma busca específica
        if not any(pattern.lower() in t.lower() for t in all_triggered):
            history = await search_anime_history(pattern)
            if history:
                deep_triggered = await process_releases(history, monitored)
                all_triggered.extend(deep_triggered)
                # Atualiza a lista local para o próximo anime não repetir downloads
                if deep_triggered:
                    monitored = await get_monitored_animes()
    
    return all_triggered
