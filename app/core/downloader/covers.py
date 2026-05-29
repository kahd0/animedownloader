"""Download e cache de imagens de capa dos animes."""
import os
import re

import httpx

from app.core.config import COVERS_DIR


async def download_cover(url, title_pattern):
    """Baixa a imagem da capa e salva em covers/. Retorna o path local ou None."""
    safe = re.sub(r'[^\w\s-]', '', title_pattern).strip().lower().replace(' ', '_')
    path = os.path.join(COVERS_DIR, f"{safe}.jpg")
    if os.path.exists(path):
        return path
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, timeout=10)
            resp.raise_for_status()
            os.makedirs(COVERS_DIR, exist_ok=True)
            with open(path, 'wb') as f:
                f.write(resp.content)
            return path
        except Exception as e:
            print(f"Erro ao baixar capa: {e}")
            return None
