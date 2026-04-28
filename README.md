# Anime Monitor

Desktop app to monitor and automatically download new anime episodes via torrents. Tracks your watchlist, fetches metadata from Jikan/MAL, and organizes files automatically.

## Features

- Monitor multiple anime series simultaneously
- Auto-detect new episode releases via SubsPlease RSS
- Trigger torrent downloads automatically (via magnet links)
- Fetch and display metadata (cover art, status, synopsis) from MyAnimeList
- Subtitle download from AnimeTosho
- Auto-organize downloaded files into the episodes folder
- System tray icon with notifications
- Import/export watchlist
- Auto-update support

## Requirements

- Python 3.11+
- `tkinter` (usually bundled; on Linux: `sudo apt install python3-tk`)
- A BitTorrent client that supports magnet links (e.g. qBittorrent)

## Installation

```bash
git clone https://github.com/kahd0/animedownloader.git
cd animedownloader
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running

```bash
source .venv/bin/activate
PYTHONPATH=. python3 main.py
```

## Project Structure

```
app/
  core/       # Config, database, API clients, download logic
  ui/         # tkinter GUI (main window, dialogs, components)
  utils/      # Async bridge, updater, episode parser
episodes/     # Final destination for downloaded video files
legendas/     # Temp directory for downloaded subtitles
covers/       # Anime cover images (downloaded at runtime)
```

## Configuration

On first run, open **Settings** to configure:

- **Episodes folder** — where organized video files are saved
- **Subtitles folder** — temp folder for downloaded `.ass` files
- **Check interval** — how often to poll for new releases (minutes)
- **Auto-organize** — automatically move completed torrents to the episodes folder
