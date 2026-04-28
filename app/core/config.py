import os
import sys

# Versão do Aplicativo
VERSION = "v1.0.4"
GITHUB_REPO = "kahd0/animedownloader"

# APIs
API_URL = "https://subsplease.org/api/?f=latest&tz=UTC"
SEARCH_URL = "https://subsplease.org/api/?f=search&tz=UTC&s="
ANIMETOSHO_API = "https://feed.animetosho.org/json"
JIKAN_API = "https://api.jikan.moe/v4"

# Quando compilado pelo PyInstaller (sys.frozen=True), __file__ aponta para o
# diretório temporário de extração. Usa sys.executable para manter dados
# persistentes (db, capas) ao lado do executável.
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
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

def get_subs_dir():
    return get_setting("subs_path", os.path.join(BASE_DIR, "legendas"))

def get_default_resolution():
    return get_setting("default_res", "1080p")

def get_check_interval():
    # Retorna em milissegundos
    try:
        minutes = int(get_setting("check_interval", "10"))
        return minutes * 60 * 1000
    except:
        return 10 * 60 * 1000

def is_auto_organize_enabled():
    return get_setting("auto_organize", "True") == "True"

def should_delete_on_watched():
    return get_setting("delete_on_watched", "True") == "True"

# Inicializa o cache
load_settings_sync()

# Atualiza as constantes dinâmicas
SUBS_TEMP_DIR = get_subs_dir()

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
