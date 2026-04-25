import aiosqlite
import os

# O banco de dados fica na raiz do projeto
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "anime_monitor.db")

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS monitored (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title_pattern TEXT NOT NULL UNIQUE,
                last_episode INTEGER DEFAULT 0,
                resolution TEXT DEFAULT '1080p'
            )
        """)
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
        async with db.execute("SELECT id, title_pattern, last_episode, resolution FROM monitored") as cursor:
            return await cursor.fetchall()

async def update_last_episode(title_pattern, episode_num):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE monitored SET last_episode = ? WHERE title_pattern = ? AND last_episode < ?",
            (episode_num, title_pattern, episode_num)
        )
        await db.commit()
