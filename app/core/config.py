import os

# APIs
API_URL = "https://subsplease.org/api/?f=latest&tz=UTC"
SEARCH_URL = "https://subsplease.org/api/?f=search&tz=UTC&s="
ANIMETOSHO_API = "https://feed.animetosho.org/json"
JIKAN_API = "https://api.jikan.moe/v4"

# Caminhos Base
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SOURCE_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "Torrents")
FINAL_DIR = os.path.join(BASE_DIR, "episodes")
SUBS_TEMP_DIR = os.path.join(BASE_DIR, "legendas")
COVERS_DIR = os.path.join(BASE_DIR, "covers")
DB_PATH = os.path.join(BASE_DIR, "anime_monitor.db")

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
