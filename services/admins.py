import hashlib
import hmac
import secrets

from config import (
    DIRECTOR_ID, LAWYER_ID, SECRETARY_ID, SUPERADMIN_IDS, WEB_ADMIN_PASSWORD, WEB_ADMIN_USER,
)
from database.db import execute, fetchall, fetchone, scalar
from utils import roles
from utils.roles import ROLE_DIRECTOR, ROLE_LAWYER, ROLE_SECRETARY, ROLE_SUPERADMIN

VALID_ROLES = (ROLE_SUPERADMIN, ROLE_DIRECTOR, ROLE_LAWYER, ROLE_SECRETARY)

# ---------------- пароли (scrypt, без внешних зависимостей) ----------------
_N, _R, _P = 2 ** 14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        _, n, r, p, salt, dk = stored.split("$")
        calc = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=32)
        return hmac.compare_digest(calc, bytes.fromhex(dk))
    except Exception:
        return False


def generate_password(length: int = 12) -> str:
    alphabet = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def password_problem(pw: str) -> str | None:
    if len(pw) < 8:
        return "Пароль должен быть не короче 8 символов."
    if pw.isdigit() or pw.isalpha():
        return "Пароль должен содержать и буквы, и цифры."
    return None


# ---------------- кэш ролей / начальное заполнение ----------------

async def refresh_roles_cache():
    rows = await fetchall("SELECT telegram_id, role FROM admins WHERE is_active=1 AND telegram_id IS NOT NULL")
    roles.set_cache({r["telegram_id"]: r["role"] for r in rows})


async def seed_admins() -> str | None:
    """Первый запуск: переносит админов из config.py в БД и создаёт веб-аккаунт суперадмина.
    Возвращает сгенерированный пароль (если он был создан), чтобы показать его в консоли один раз."""
    generated = None
    if await scalar("SELECT COUNT(*) FROM admins") == 0:
        for i, tg in enumerate(SUPERADMIN_IDS):
            await execute(
                "INSERT OR IGNORE INTO admins (telegram_id, full_name, role) VALUES (?,?,?)",
                (tg, f"Суперадмин {i + 1}" if len(SUPERADMIN_IDS) > 1 else "Суперадмин", ROLE_SUPERADMIN),
            )
        for tg, name, role in (
            (DIRECTOR_ID, "Руководитель", ROLE_DIRECTOR),
            (LAWYER_ID, "Юрист", ROLE_LAWYER),
            (SECRETARY_ID, "Секретарь", ROLE_SECRETARY),
        ):
            await execute("INSERT OR IGNORE INTO admins (telegram_id, full_name, role) VALUES (?,?,?)", (tg, name, role))

    # Веб-доступ суперадмина: если ни у одного суперадмина нет логина — создаём
    if not await scalar("SELECT COUNT(*) FROM admins WHERE role='superadmin' AND username IS NOT NULL"):
        first = await fetchone("SELECT id FROM admins WHERE role='superadmin' ORDER BY id LIMIT 1")
        password = WEB_ADMIN_PASSWORD or generate_password(14)
        if not WEB_ADMIN_PASSWORD:
            generated = password
        if first:
            await execute(
                "UPDATE admins SET username=?, password_hash=?, must_change_pw=? WHERE id=?",
                (WEB_ADMIN_USER, hash_password(password), 0 if WEB_ADMIN_PASSWORD else 1, first["id"]),
            )
        else:
            await execute(
                "INSERT INTO admins (username, full_name, role, password_hash, must_change_pw) VALUES (?,?,?,?,?)",
                (WEB_ADMIN_USER, "Суперадмин", ROLE_SUPERADMIN, hash_password(password), 0 if WEB_ADMIN_PASSWORD else 1),
            )
    await refresh_roles_cache()
    return generated


# ---------------- запросы ----------------

async def get_by_id(admin_id: int):
    return await fetchone("SELECT * FROM admins WHERE id=?", (admin_id,))


async def get_by_telegram(tg_id: int):
    return await fetchone("SELECT * FROM admins WHERE telegram_id=? AND is_active=1", (tg_id,))


async def get_by_username(username: str):
    return await fetchone("SELECT * FROM admins WHERE username=? COLLATE NOCASE", (username,))


async def list_admins():
    return await fetchall("SELECT * FROM admins ORDER BY is_active DESC, role, id")


async def active_superadmin_count(exclude_id: int | None = None) -> int:
    return await scalar(
        "SELECT COUNT(*) FROM admins WHERE role='superadmin' AND is_active=1 AND id != ?", (exclude_id or 0,)
    )


async def create_admin(full_name: str, role: str, telegram_id: int | None = None,
                       username: str | None = None, password: str | None = None) -> int:
    if role not in VALID_ROLES:
        raise ValueError("Недопустимая роль")
    admin_id = await execute(
        "INSERT INTO admins (telegram_id, username, full_name, role, password_hash, must_change_pw) VALUES (?,?,?,?,?,?)",
        (telegram_id, username or None, full_name, role, hash_password(password) if password else None, 1 if password else 0),
    )
    await refresh_roles_cache()
    return admin_id


async def update_admin(admin_id: int, **fields):
    allowed = {"full_name", "role", "telegram_id", "username", "is_active"}
    sets, params = [], []
    for k, v in fields.items():
        if k in allowed:
            sets.append(f"{k}=?"); params.append(v)
    if not sets:
        return
    await execute(f"UPDATE admins SET {', '.join(sets)} WHERE id=?", tuple(params) + (admin_id,))
    if fields.get("is_active") == 0:
        await execute("DELETE FROM web_sessions WHERE admin_id=?", (admin_id,))
    await refresh_roles_cache()


async def set_password(admin_id: int, password: str, must_change: bool = False):
    await execute(
        "UPDATE admins SET password_hash=?, must_change_pw=? WHERE id=?",
        (hash_password(password), 1 if must_change else 0, admin_id),
    )
    await execute("DELETE FROM web_sessions WHERE admin_id=?", (admin_id,))


async def delete_admin(admin_id: int):
    await execute("DELETE FROM admins WHERE id=?", (admin_id,))
    await refresh_roles_cache()
