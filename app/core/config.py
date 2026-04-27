import os

# Versão do Aplicativo
VERSION = "v1.0.1"
GITHUB_REPO = "seu-usuario/seu-repositorio"

# APIs
API_URL = "https://subsplease.org/api/?f=latest&tz=UTC"
SEARCH_URL = "https://subsplease.org/api/?f=search&tz=UTC&s="
ANIMETOSHO_API = "https://feed.animetosho.org/json"
JIKAN_API = "https://api.jikan.moe/v4"

# Caminhos Base fixos
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
COVERS_DIR = os.path.join(BASE_DIR, "covers")
DB_PATH = os.path.join(BASE_DIR, "anime_monitor.db")
SUBS_TEMP_DIR = os.path.join(BASE_DIR, "legendas")

# Cache de configurações
_SETTINGS_CACHE = {}

def load_settings_sync():
    """Carrega configurações do banco de dados de forma síncrona (fallback/inicialização)."""
    import sqlite3
    global _SETTINGS_CACHE
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        cursor.execute("SELECT key, value FROM settings")
        for key, value in cursor.fetchall():
            _SETTINGS_CACHE[key] = value
        conn.close()
    except Exception as e:
        print(f"Erro ao carregar configurações: {e}")

def get_setting(key, default):
    return _SETTINGS_CACHE.get(key, default)

def get_source_dir():
    return get_setting("download_path", os.path.join(os.path.expanduser("~"), "Downloads", "Torrents"))

def get_final_dir():
    return get_setting("organize_path", os.path.join(BASE_DIR, "episodes"))

# Inicializa o cache
load_settings_sync()

# UI Constants
STATUS_COLORS = {
    "Currently Airing": "#4caf50",
    "Finished Airing":  "#888888",
    "Not yet aired":    "#2196f3",
}

STATUS_PT = {
    "Currently Airing": "Em Exibição",
    "Finished Airing":  "Finalizado",
    "Not yet aired":    "Em Breve",
}

COVER_W, COVER_H = 140, 200
