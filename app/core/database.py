import aiosqlite
from datetime import datetime
from .config import DB_PATH

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS monitored (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title_pattern TEXT NOT NULL UNIQUE,
                last_episode INTEGER DEFAULT 0,
                resolution TEXT DEFAULT '1080p',
                last_download_date TEXT DEFAULT NULL,
                cover_url TEXT DEFAULT NULL,
                official_title TEXT DEFAULT NULL,
                airing_status TEXT DEFAULT NULL,
                has_new_episode INTEGER DEFAULT 0
            )
        """)
        for col, definition in [
            ("last_download_date", "TEXT DEFAULT NULL"),
            ("cover_url",          "TEXT DEFAULT NULL"),
            ("official_title",     "TEXT DEFAULT NULL"),
            ("airing_status",      "TEXT DEFAULT NULL"),
            ("has_new_episode",    "INTEGER DEFAULT 0"),
        ]:
            try:
                await db.execute(f"ALTER TABLE monitored ADD COLUMN {col} {definition}")
            except Exception:
                pass
        await db.commit()

async def add_anime(title_pattern, resolution='1080p', start_episode=0):
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO monitored (title_pattern, resolution, last_episode) VALUES (?, ?, ?)",
                (title_pattern, resolution, start_episode)
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

async def remove_anime(anime_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM monitored WHERE id = ?", (anime_id,))
        await db.commit()

async def get_monitored_animes():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT id, title_pattern, last_episode, resolution, last_download_date,
                      cover_url, official_title, airing_status, has_new_episode
               FROM monitored"""
        ) as cursor:
            return await cursor.fetchall()

async def update_last_episode(title_pattern, episode_num):
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE monitored
               SET last_episode = ?, last_download_date = ?, has_new_episode = 1
               WHERE title_pattern = ? AND last_episode < ?""",
            (episode_num, now, title_pattern, episode_num)
        )
        await db.commit()

async def update_anime_metadata(anime_id, official_title, cover_url, airing_status):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE monitored
               SET official_title = ?, cover_url = ?, airing_status = ?
               WHERE id = ?""",
            (official_title, cover_url, airing_status, anime_id)
        )
        await db.commit()

async def set_last_episode(anime_id, episode_num):
    """Atualiza o episódio incondicionalmente (para correções manuais)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE monitored SET last_episode = ? WHERE id = ?",
            (episode_num, anime_id)
        )
        await db.commit()

async def clear_new_episode_flag(anime_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE monitored SET has_new_episode = 0 WHERE id = ?", (anime_id,)
        )
        await db.commit()
