# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
bash run_downloader.sh
```

This activates `.venv`, sets `PYTHONPATH` to `app/`, and launches the tkinter GUI.

To run directly (with venv already active):
```bash
PYTHONPATH=app python3 app/subsplease_downloader.py
```

## Dependencies

```bash
pip install -r requirements.txt  # textual, httpx, aiosqlite
```

`tkinter` is used for the GUI and is part of the Python standard library (no pip install needed). If missing on Linux: `sudo apt install python3-tk`.

## Architecture

The app is split into three modules under `app/`:

**`database.py`** — All SQLite access via `aiosqlite`. Single table `monitored` (id, title_pattern, last_episode, resolution). Every function is an `async def`. The DB file lives at the project root as `anime_monitor.db`.

**`downloader.py`** — All business logic. No UI dependencies. Key functions:
- `fetch_latest_releases()` / `search_anime_history(query)` — hit SubsPlease API
- `download_subtitle(show_name, ep_num)` — queries AnimeTosho, downloads XZ-compressed subtitle, decompresses it to `legendas/`
- `trigger_magnet(link)` — opens the magnet link in the system torrent client via `xdg-open` (Linux), `open` (macOS), `os.startfile` (Windows)
- `organize_downloads()` — moves completed `.mkv/.mp4/.avi` files from `~/Downloads/Torrents` to `episodes/`, then pairs subtitles from `legendas/` by matching `_epXX` in the filename
- `process_releases(releases_list)` — core loop: for each release, checks if it matches a monitored pattern and exceeds `last_episode`, triggers magnet, downloads subtitle, updates DB
- `check_for_updates()` — calls `fetch_latest_releases()`, then for any monitored anime not in the latest feed, falls back to `search_anime_history()`

**`subsplease_downloader.py`** — tkinter GUI (`AnimeMonitorApp(tk.Tk)`).

### Async/Threading bridge

The GUI is synchronous tkinter; all I/O is async. The bridge pattern:

```python
_loop = asyncio.new_event_loop()
threading.Thread(target=_loop.run_forever, daemon=True).start()

def run_async(coro, on_done=None):
    future = asyncio.run_coroutine_threadsafe(coro, _loop)
    if on_done:
        future.add_done_callback(lambda f: app_ref.after(0, lambda: on_done(f.result())))
```

All UI updates inside `on_done` callbacks are safe because `app_ref.after(0, ...)` marshals them back to the tkinter main thread.

### Adding a new anime — flow

1. User types name, hits Enter / clicks "Adicionar"
2. If input has `:` → parse `name:episode` directly, skip dialog
3. Otherwise → `run_async(search_anime_history(name))` → on result, open `tk.Toplevel` modal with a `ttk.Spinbox` pre-filled at `max_ep - 2`
4. On confirm → `add_anime(name, start_episode=chosen)` → `process_releases(history)`

### Directory layout

| Path | Purpose |
|------|---------|
| `episodes/` | Final destination for downloaded video files |
| `legendas/` | Temp directory for downloaded subtitles (before pairing) |
| `~/Downloads/Torrents` | Source watched by `organize_downloads()` for completed torrents |

### External APIs

- `https://subsplease.org/api/` — latest releases (`?f=latest`) and search (`?f=search&s=`)
- `https://feed.animetosho.org/json` — subtitle search and attachment download; subtitles stored at `https://storage.animetosho.org/attach/{id:08x}/file.xz`

### Subtitle selection priority

PT-BR non-forced/non-CC → PT-BR forced/CC → English → other. Implemented in `download_subtitle()` via `sort_key`.
