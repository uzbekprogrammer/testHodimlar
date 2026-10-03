import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _load_env(path: Path) -> None:
    """Минимальный загрузчик .env (без внешних зависимостей). Уже заданные переменные окружения не перезаписываются."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env(BASE_DIR / ".env")

# --- Bot tokeni: faqat .env yoki environment orqali (kodda saqlanmaydi) ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi: uni .env faylida yoki environment variable sifatida bering.")

BOT_NAME_RU = "Обращение бот"
PLATFORM_NAME = "Toshkent EM"

# --- Boshlang'ich adminlar (faqat admins jadvali bo'sh bo'lganda bir marta yoziladi) ---
# Keyinchalik adminlar bot paneli yoki sayt orqali boshqariladi.
SUPERADMIN_IDS = [1768033194]
DIRECTOR_ID = 141757010
LAWYER_ID = 807474201
SECRETARY_ID = 5222441602

# --- Ma'lumotlar bazasi ---
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "database" / "bot.db"))

# --- Ogohlantirish hujjatlari ---
WARNING_DOC_UZ = "assets/ogohlantirish_uz.docx"
WARNING_DOC_RU = "assets/ogohlantirish_ru.docx"

# --- Direktor qabuli sozlamalari ---
WORK_START_HOUR = 8
WORK_END_HOUR = 16
LUNCH_START_HOUR = 12
LUNCH_END_HOUR = 13
RECEPTION_DAYS_AHEAD = 5

# --- Veb-sayt ---
WEB_HOST = os.getenv("WEB_HOST", "127.0.0.1")
WEB_PORT = int(os.getenv("WEB_PORT", "8000"))
WEB_SECURE_COOKIES = os.getenv("WEB_SECURE_COOKIES", "0") == "1"   # HTTPS ortida 1 qiling
TRUST_PROXY = os.getenv("TRUST_PROXY", "0") == "1"                  # reverse-proxy ortida 1 qiling
WEB_ADMIN_USER = os.getenv("WEB_ADMIN_USER", "admin")
WEB_ADMIN_PASSWORD = os.getenv("WEB_ADMIN_PASSWORD", "")            # bo'sh bo'lsa, birinchi ishga tushishda tasodifiy yaratiladi
SESSION_IDLE_MINUTES = 60 * 8
SESSION_MAX_HOURS = 24
# Superadmin murojaat matnini ko'ra oladimi (avvalgi qoida: yo'q, faqat qisqa ma'lumot)
SUPERADMIN_SEE_APPEAL_TEXT = os.getenv("SUPERADMIN_SEE_APPEAL_TEXT", "0") == "1"
