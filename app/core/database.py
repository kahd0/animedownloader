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
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        # v2 tables
        await db.execute("""
            CREATE TABLE IF NOT EXISTS releases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                anime_id INTEGER,
                episode INTEGER,
                title TEXT,
                magnet TEXT,
                torrent_hash TEXT,
                resolution TEXT,
                source TEXT,
                score INTEGER DEFAULT 0,
                created_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS anime_aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                anime_id INTEGER,
                alias TEXT,
                UNIQUE(anime_id, alias)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS subtitle_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                anime_id INTEGER,
                episode INTEGER,
                provider TEXT,
                language TEXT,
                filename TEXT,
                file_hash TEXT UNIQUE,
                created_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS translation_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text_hash TEXT UNIQUE,
                original TEXT,
                translated TEXT,
                provider TEXT,
                created_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS glossary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_term TEXT NOT NULL UNIQUE,
                target_term TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                anime_id INTEGER,
                episode INTEGER,
                status TEXT DEFAULT 'pending',
                retries INTEGER DEFAULT 0,
                error TEXT,
                payload TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level TEXT,
                source TEXT,
                message TEXT,
                created_at TEXT
            )
        """)
        for col, definition in [
            ("last_download_date", "TEXT DEFAULT NULL"),
            ("cover_url",          "TEXT DEFAULT NULL"),
            ("official_title",     "TEXT DEFAULT NULL"),
            ("airing_status",      "TEXT DEFAULT NULL"),
            ("has_new_episode",    "INTEGER DEFAULT 0"),
            ("last_downloaded",    "INTEGER DEFAULT 0"),
            ("total_episodes",     "INTEGER DEFAULT NULL"),
            ("score",              "REAL DEFAULT NULL"),
            ("studio",             "TEXT DEFAULT NULL"),
            ("season",             "TEXT DEFAULT NULL"),
            ("mal_year",           "INTEGER DEFAULT NULL"),
            ("synopsis",           "TEXT DEFAULT NULL"),
            ("last_ready",         "INTEGER DEFAULT 0"),
        ]:
            try:
                await db.execute(f"ALTER TABLE monitored ADD COLUMN {col} {definition}")
            except Exception:
                pass
        await db.commit()
        await db.execute(
            "UPDATE monitored SET last_downloaded = last_episode WHERE last_downloaded = 0 AND last_episode > 0"
        )
        await db.commit()
        await db.execute(
            "UPDATE monitored SET last_ready = last_downloaded WHERE last_ready IS NULL OR (last_ready = 0 AND last_downloaded > 0)"
        )
        await db.commit()

async def get_setting(key, default=None):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else default

async def set_setting(key, value):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, str(value))
        )
        await db.commit()

async def add_anime(title_pattern, resolution='1080p', start_episode=0):
    # start_episode is the FIRST episode to download (inclusive).
    # last_downloaded = start_episode - 1 so the condition (last_downloaded < ep) includes it.
    last_dl = max(0, start_episode - 1)
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO monitored (title_pattern, resolution, last_episode, last_downloaded) VALUES (?, ?, ?, ?)",
                (title_pattern, resolution, last_dl, last_dl)
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
                      cover_url, official_title, airing_status, has_new_episode, last_downloaded,
                      total_episodes, score, studio, season, mal_year, synopsis, last_ready
               FROM monitored"""
        ) as cursor:
            return await cursor.fetchall()

async def import_animes(anime_list):
    """Importa uma lista de dicionários contendo os dados dos animes."""
    async with aiosqlite.connect(DB_PATH) as db:
        for anime in anime_list:
            try:
                await db.execute(
                    """INSERT OR REPLACE INTO monitored 
                       (title_pattern, last_episode, resolution, official_title, cover_url, airing_status) 
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        anime.get('title_pattern'),
                        anime.get('last_episode', 0),
                        anime.get('resolution', '1080p'),
                        anime.get('official_title'),
                        anime.get('cover_url'),
                        anime.get('airing_status')
                    )
                )
            except Exception as e:
                print(f"Erro ao importar anime {anime.get('title_pattern')}: {e}")
        await db.commit()

async def update_last_episode(title_pattern, episode_num):
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE monitored
               SET last_downloaded = ?, last_download_date = ?, has_new_episode = 1
               WHERE title_pattern = ? AND last_downloaded < ?""",
            (episode_num, now, title_pattern, episode_num)
        )
        await db.commit()

async def mark_episode_queued(title_pattern: str, episode_num: int):
    """Mark episode as queued for download (prevents re-queueing). Does NOT trigger the watch badge."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE monitored SET last_downloaded = ? WHERE title_pattern = ? AND last_downloaded < ?",
            (episode_num, title_pattern, episode_num)
        )
        await db.commit()

async def mark_episode_ready(title_pattern: str, episode_num: int):
    """Mark episode as ready to watch (file is on disk). Triggers the watch badge."""
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE monitored
               SET last_ready = ?, last_download_date = ?, has_new_episode = 1
               WHERE title_pattern = ? AND (last_ready IS NULL OR last_ready < ?)""",
            (episode_num, now, title_pattern, episode_num)
        )
        await db.commit()

async def update_anime_metadata(anime_id, official_title, cover_url, airing_status,
                                total_episodes=None, score=None, studio=None,
                                season=None, mal_year=None, synopsis=None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE monitored
               SET official_title = ?, cover_url = ?, airing_status = ?,
                   total_episodes = ?, score = ?, studio = ?, season = ?, mal_year = ?, synopsis = ?
               WHERE id = ?""",
            (official_title, cover_url, airing_status,
             total_episodes, score, studio, season, mal_year, synopsis, anime_id)
        )
        await db.commit()

async def set_last_episode(anime_id, episode_num):
    """Atualiza o episódio incondicionalmente (para correções manuais)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE monitored
               SET last_episode = ?,
                   last_downloaded = MAX(last_downloaded, ?),
                   last_ready = MAX(last_ready, ?),
                   has_new_episode = 0
               WHERE id = ?""",
            (episode_num, episode_num, episode_num, anime_id)
        )
        await db.commit()

async def clear_new_episode_flag(anime_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE monitored SET has_new_episode = 0 WHERE id = ?", (anime_id,)
        )
        await db.commit()


# ---------- v2: releases ----------

async def save_release(anime_id: int, episode: int, title: str, magnet: str,
                        torrent_hash: str | None, resolution: str, source: str, score: int = 0):
    now = datetime.now().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO releases (anime_id, episode, title, magnet, torrent_hash, resolution, source, score, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (anime_id, episode, title, magnet, torrent_hash, resolution, source, score, now),
        )
        await db.commit()


async def get_releases(anime_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT * FROM releases WHERE anime_id = ? ORDER BY created_at DESC", (anime_id,)
        ) as cursor:
            return await cursor.fetchall()


# ---------- v2: aliases ----------

async def add_alias(anime_id: int, alias: str):
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO anime_aliases (anime_id, alias) VALUES (?, ?)", (anime_id, alias)
            )
            await db.commit()
        except Exception:
            pass


async def get_aliases(anime_id: int) -> list[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT alias FROM anime_aliases WHERE anime_id = ?", (anime_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [r[0] for r in rows]


# ---------- v2: subtitle cache ----------

async def get_cached_subtitle(anime_id: int, episode: int, language: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT provider, language, filename, file_hash FROM subtitle_cache
               WHERE anime_id = ? AND episode = ? AND language = ?
               ORDER BY id DESC LIMIT 1""",
            (anime_id, episode, language),
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return {"provider": row[0], "language": row[1], "filename": row[2], "file_hash": row[3]}


async def save_subtitle_cache(anime_id: int, episode: int, provider: str,
                               language: str, filename: str, file_hash: str):
    now = datetime.now().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                """INSERT INTO subtitle_cache (anime_id, episode, provider, language, filename, file_hash, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (anime_id, episode, provider, language, filename, file_hash, now),
            )
            await db.commit()
        except Exception:
            pass


# ---------- v2: translation memory ----------

async def get_translation(text_hash: str) -> str | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT translated FROM translation_memory WHERE text_hash = ?", (text_hash,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


async def save_translation(text_hash: str, original: str, translated: str, provider: str):
    now = datetime.now().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                """INSERT INTO translation_memory (text_hash, original, translated, provider, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (text_hash, original, translated, provider, now),
            )
            await db.commit()
        except Exception as e:
            print(f"[DB] save_translation erro: {e}")


# ---------- v2: glossary ----------

async def get_glossary() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id, source_term, target_term FROM glossary") as cursor:
            rows = await cursor.fetchall()
            return [{"id": r[0], "source": r[1], "target": r[2]} for r in rows]


async def upsert_glossary_term(source_term: str, target_term: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO glossary (source_term, target_term) VALUES (?, ?)",
            (source_term, target_term),
        )
        await db.commit()


async def delete_glossary_term(term_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM glossary WHERE id = ?", (term_id,))
        await db.commit()


# ---------- v2: jobs ----------

async def enqueue_job(job_type: str, anime_id: int | None = None,
                       episode: int | None = None, payload: str | None = None) -> int:
    now = datetime.now().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO jobs (type, anime_id, episode, status, payload, created_at, updated_at)
               VALUES (?, ?, ?, 'pending', ?, ?, ?)""",
            (job_type, anime_id, episode, payload, now, now),
        )
        await db.commit()
        return cursor.lastrowid


async def update_job_status(job_id: int, status: str, error: str | None = None):
    now = datetime.now().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE jobs SET status = ?, error = ?, updated_at = ? WHERE id = ?",
            (status, error, now, job_id),
        )
        await db.commit()


async def get_active_jobs() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT * FROM jobs WHERE status IN ('pending', 'running') ORDER BY created_at"
        ) as cursor:
            return await cursor.fetchall()


async def get_failed_jobs() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT * FROM jobs WHERE status = 'failed' AND retries < 3 ORDER BY created_at"
        ) as cursor:
            return await cursor.fetchall()


async def increment_job_retry(job_id: int):
    now = datetime.now().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE jobs SET retries = retries + 1, status = 'pending', updated_at = ? WHERE id = ?",
            (now, job_id),
        )
        await db.commit()


# ---------- v2: subtitle helpers ----------

async def get_subtitled_episodes(anime_id: int) -> set[int]:
    """Return set of episode numbers that have at least one subtitle_cache entry (any language)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT DISTINCT episode FROM subtitle_cache WHERE anime_id = ?",
            (anime_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return {r[0] for r in rows}


async def get_ptbr_subtitled_episodes(anime_id: int) -> set[int]:
    """Return set of episode numbers that have a PT-BR subtitle_cache entry."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT DISTINCT episode FROM subtitle_cache
               WHERE anime_id = ? AND (LOWER(language) LIKE '%pt%' OR LOWER(language) LIKE '%por%')""",
            (anime_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return {r[0] for r in rows}


async def get_all_pending_counts() -> dict[int, dict]:
    """
    Returns {anime_id: {'need_subtitle': N, 'need_translation': N}}
    where:
      - need_subtitle = episodes in (last_downloaded..last_episode] with no subtitle entry
      - need_translation = episodes in (last_downloaded..last_episode] that have subtitle but no pt-br
    """
    async with aiosqlite.connect(DB_PATH) as db:
        # Get all monitored animes
        async with db.execute(
            "SELECT id, last_downloaded, last_episode FROM monitored"
        ) as cursor:
            animes = await cursor.fetchall()

        # Get all subtitle cache entries
        async with db.execute(
            "SELECT anime_id, episode, language FROM subtitle_cache"
        ) as cursor:
            sub_rows = await cursor.fetchall()

    # Build sets
    subtitled: dict[int, set[int]] = {}       # anime_id -> set of ep numbers with ANY subtitle
    ptbr_subtitled: dict[int, set[int]] = {}  # anime_id -> set of ep numbers with PT-BR subtitle

    for anime_id, episode, language in sub_rows:
        subtitled.setdefault(anime_id, set()).add(episode)
        lang_lower = (language or "").lower()
        if "pt" in lang_lower or "por" in lang_lower:
            ptbr_subtitled.setdefault(anime_id, set()).add(episode)

    result = {}
    for anime_id, last_dl, last_ep in animes:
        if last_ep <= last_dl:
            result[anime_id] = {"need_subtitle": 0, "need_translation": 0}
            continue
        pending_eps = set(range(last_dl + 1, last_ep + 1))
        with_sub = subtitled.get(anime_id, set())
        with_ptbr = ptbr_subtitled.get(anime_id, set())
        need_subtitle = len(pending_eps - with_sub)
        need_translation = len((pending_eps & with_sub) - with_ptbr)
        result[anime_id] = {"need_subtitle": need_subtitle, "need_translation": need_translation}

    return result
