"""Безопасность сайта: сессии на стороне сервера, CSRF, ограничение попыток входа, IP клиента."""
import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta

from fastapi import Request

from config import SESSION_IDLE_MINUTES, SESSION_MAX_HOURS, TRUST_PROXY
from database.db import execute, fetchone

COOKIE = "tem_session"
LOGIN_CSRF_COOKIE = "tem_login"


def client_ip(request: Request) -> str:
    if TRUST_PROXY:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()[:45]
    return (request.client.host if request.client else "unknown")[:45]


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def safe_equal(a: str, b: str) -> bool:
    return bool(a) and bool(b) and hmac.compare_digest(a.encode(), b.encode())


async def create_session(admin_id: int, ip: str, user_agent: str) -> tuple[str, str]:
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    await execute(
        "INSERT INTO web_sessions (token_hash, admin_id, csrf, ip, user_agent) VALUES (?,?,?,?,?)",
        (_hash(token), admin_id, csrf, ip, (user_agent or "")[:200]),
    )
    await execute("UPDATE admins SET last_login=datetime('now') WHERE id=?", (admin_id,))
    return token, csrf


async def load_session(token: str | None) -> dict | None:
    """Возвращает {'admin': ..., 'csrf': ..., 'session_id': ...} или None (нет сессии / истекла / аккаунт отключён)."""
    if not token:
        return None
    row = await fetchone(
        """SELECT s.id AS sid, s.csrf, s.created_at, s.last_seen, a.*
           FROM web_sessions s JOIN admins a ON a.id = s.admin_id
           WHERE s.token_hash = ?""",
        (_hash(token),),
    )
    if not row or not row["is_active"]:
        return None
    now = datetime.utcnow()
    try:
        created = datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S")
        seen = datetime.strptime(row["last_seen"], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    if now - created > timedelta(hours=SESSION_MAX_HOURS) or now - seen > timedelta(minutes=SESSION_IDLE_MINUTES):
        await execute("DELETE FROM web_sessions WHERE id=?", (row["sid"],))
        return None
    if now - seen > timedelta(seconds=60):   # не пишем в БД на каждый запрос
        await execute("UPDATE web_sessions SET last_seen=datetime('now') WHERE id=?", (row["sid"],))
    admin = {k: row[k] for k in ("id", "telegram_id", "username", "full_name", "role", "is_active", "must_change_pw", "last_login")}
    return {"admin": admin, "csrf": row["csrf"], "session_id": row["sid"]}


async def destroy_session(token: str | None):
    if token:
        await execute("DELETE FROM web_sessions WHERE token_hash=?", (_hash(token),))


async def purge_expired():
    await execute(
        "DELETE FROM web_sessions WHERE last_seen < datetime('now', ?) OR created_at < datetime('now', ?)",
        (f"-{SESSION_IDLE_MINUTES} minutes", f"-{SESSION_MAX_HOURS} hours"),
    )


class LoginLimiter:
    """Блокировка перебора паролей: окно 15 минут, лимиты отдельно по IP и по логину."""
    WINDOW = 15 * 60
    MAX_PER_IP = 10
    MAX_PER_USER = 5

    def __init__(self):
        self._fails: dict[str, list[float]] = {}

    def _recent(self, key: str) -> list[float]:
        now = time.monotonic()
        lst = [t for t in self._fails.get(key, []) if now - t < self.WINDOW]
        if lst:
            self._fails[key] = lst
        else:
            self._fails.pop(key, None)
        return lst

    def locked(self, ip: str, username: str) -> bool:
        return (len(self._recent(f"ip:{ip}")) >= self.MAX_PER_IP
                or len(self._recent(f"u:{username.lower()}")) >= self.MAX_PER_USER)

    def fail(self, ip: str, username: str):
        now = time.monotonic()
        for key in (f"ip:{ip}", f"u:{username.lower()}"):
            self._fails.setdefault(key, []).append(now)
        if len(self._fails) > 10000:
            for k in list(self._fails):
                self._recent(k)

    def reset(self, ip: str, username: str):
        self._fails.pop(f"u:{username.lower()}", None)


limiter = LoginLimiter()
