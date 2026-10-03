import asyncio
import aiosqlite

from config import DB_PATH

_conn: aiosqlite.Connection | None = None
_lock = asyncio.Lock()


async def get_conn() -> aiosqlite.Connection:
    """Единое долгоживущее соединение (быстрее, чем открывать БД на каждый запрос). WAL позволяет читать параллельно с записью."""
    global _conn
    if _conn is None:
        async with _lock:
            if _conn is None:
                conn = await aiosqlite.connect(DB_PATH)
                conn.row_factory = aiosqlite.Row
                await conn.execute("PRAGMA journal_mode=WAL")
                await conn.execute("PRAGMA synchronous=NORMAL")
                await conn.execute("PRAGMA foreign_keys=ON")
                await conn.execute("PRAGMA temp_store=MEMORY")
                await conn.execute("PRAGMA cache_size=-20000")
                await conn.execute("PRAGMA busy_timeout=5000")
                _conn = conn
    return _conn


async def close_db():
    global _conn
    if _conn is not None:
        await _conn.close()
        _conn = None


async def fetchall(sql: str, params: tuple = ()) -> list[dict]:
    conn = await get_conn()
    cur = await conn.execute(sql, params)
    rows = await cur.fetchall()
    await cur.close()
    return [dict(r) for r in rows]


async def fetchone(sql: str, params: tuple = ()) -> dict | None:
    conn = await get_conn()
    cur = await conn.execute(sql, params)
    row = await cur.fetchone()
    await cur.close()
    return dict(row) if row else None


async def scalar(sql: str, params: tuple = ()):
    row = await fetchone(sql, params)
    return next(iter(row.values())) if row else None


async def execute(sql: str, params: tuple = ()) -> int:
    """INSERT/UPDATE/DELETE + commit. Возвращает lastrowid."""
    conn = await get_conn()
    cur = await conn.execute(sql, params)
    await conn.commit()
    last = cur.lastrowid
    await cur.close()
    return last


async def _add_column(conn, table: str, column: str, ddl: str):
    cur = await conn.execute(f"PRAGMA table_info({table})")
    cols = {r["name"] for r in await cur.fetchall()}
    await cur.close()
    if column not in cols:
        await conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


async def init_db():
    """Создаёт таблицы, добавляет недостающие колонки (миграция), индексы."""
    conn = await get_conn()

    await conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            username TEXT,
            full_name TEXT,
            position TEXT,
            department TEXT,
            phone TEXT,
            registered_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS appeals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL,
            username TEXT,
            full_name TEXT,
            appeal_type TEXT NOT NULL,      -- corruption / personal / taklif
            text TEXT,
            file_id TEXT,
            file_type TEXT,                 -- photo / document
            status TEXT DEFAULT 'yangi',    -- yangi / v_rabote / javob_berildi
            admin_comment TEXT,
            answered_by TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            answered_at TEXT
        );

        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL,
            full_name TEXT,
            phone TEXT,
            reason TEXT,
            appointment_date TEXT NOT NULL,
            appointment_time TEXT NOT NULL,
            status TEXT DEFAULT 'kutilmoqda',  -- kutilmoqda / tasdiqlandi / rad_etildi
            director_comment TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            decided_at TEXT
        );

        -- Администраторы (бот + сайт). telegram_id нужен для бота, username/password_hash - для входа на сайт.
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE,
            username TEXT UNIQUE,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL,             -- superadmin / director / lawyer / secretary
            password_hash TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            must_change_pw INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            last_login TEXT
        );

        CREATE TABLE IF NOT EXISTS web_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_hash TEXT UNIQUE NOT NULL,
            admin_id INTEGER NOT NULL REFERENCES admins(id) ON DELETE CASCADE,
            csrf TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            last_seen TEXT DEFAULT (datetime('now')),
            ip TEXT,
            user_agent TEXT
        );

        -- История действий (бот, сайт, система)
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT DEFAULT (datetime('now')),
            source TEXT NOT NULL,           -- bot / web / system
            actor_id INTEGER,               -- admins.id (может быть NULL)
            actor_name TEXT,
            actor_role TEXT,
            action TEXT NOT NULL,
            entity TEXT,
            entity_id TEXT,
            details TEXT,
            ip TEXT
        );
        """
    )

    await _add_column(conn, "appeals", "updated_at", "TEXT")
    await _add_column(conn, "appeals", "answered_by_id", "INTEGER")
    await _add_column(conn, "appointments", "decided_by", "TEXT")

    await conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_appeals_status ON appeals(status, created_at);
        CREATE INDEX IF NOT EXISTS idx_appeals_type ON appeals(appeal_type);
        CREATE INDEX IF NOT EXISTS idx_appeals_tg ON appeals(telegram_id);
        CREATE INDEX IF NOT EXISTS idx_appeals_created ON appeals(created_at);
        CREATE INDEX IF NOT EXISTS idx_appt_date ON appointments(appointment_date, status);
        CREATE INDEX IF NOT EXISTS idx_appt_tg ON appointments(telegram_id);
        CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts);
        CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action);
        CREATE INDEX IF NOT EXISTS idx_sessions_admin ON web_sessions(admin_id);
        CREATE INDEX IF NOT EXISTS idx_users_name ON users(full_name);
        """
    )
    await conn.commit()
