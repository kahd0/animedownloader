# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
bash run_downloader.sh
```

This activates `.venv`, sets `PYTHONPATH` to project root, and launches `main.py`.

To run directly (with venv already active):
```bash
PYTHONPATH=. python3 main.py
```

## Dependencies

```bash
pip install -r requirements.txt  # textual, httpx, aiosqlite, pystray, pillow
```

`tkinter` is used for the GUI and is part of the Python standard library. If missing on Linux: `sudo apt install python3-tk`.

## Architecture

The app is organized into a modular structure under `app/`:

### Core (`app/core/`)
- **`config.py`**: Paths, API URLs, and UI constants.
- **`database.py`**: All SQLite access via `aiosqlite`. DB path is defined in `config.py`.
- **`api.py`**: Direct interactions with external APIs (SubsPlease, Jikan, AnimeTosho).
- **`downloader.py`**: Business logic, file organization, magnet triggering, and subtitle selection coordination.

### UI (`app/ui/`)
- **`main_window.py`**: Main tkinter GUI (`AnimeMonitorApp`).
- **`tray.py`**: System tray icon and notifications logic.
- **`styles.py`**: Theme and widget styling definitions.

### Utils (`app/utils/`)
- **`async_bridge.py`**: Bridge between sync tkinter and async logic using a dedicated event loop thread.

## Directory Layout

| Path | Purpose |
|------|---------|
| `episodes/` | Final destination for downloaded video files |
| `legendas/` | Temp directory for downloaded subtitles |
| `covers/` | Storage for anime cover images |
| `~/Downloads/Torrents` | Source directory for completed torrents |

## Async/Threading Bridge

The GUI is synchronous; all I/O is async. Use `run_async(coro, on_done=None)` from `app.utils.async_bridge`. `on_done` callbacks are automatically marshaled back to the tkinter thread.
