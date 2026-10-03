"""Общая логика приёма обращений (коррупция / личный вопрос / предложение) — без дублирования в трёх файлах."""
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from database.models import create_appeal, get_user
from keyboards.inline import appeal_admin_kb
from keyboards.reply import main_menu_kb
from services import audit
from services.core import dispatch_appeal, esc
from utils.notifications import notify_superadmins

MAX_TEXT = 3500

KINDS = {
    "corruption": {
        "db_type": "corruption",
        "title": "🔴 <b>YANGI KORRUPSIYA MUROJAATI</b>",
        "ok": "✅ Murojaatingiz qabul qilindi. Murojaat raqami: #{id}",
        "summary": "Yangi korrupsiya murojaati",
        "anonymous": True,
    },
    "personal": {
        "db_type": "personal",
        "title": "👤 <b>YANGI SHAXSIY MUROJAAT</b>",
        "ok": "✅ Murojaatingiz qabul qilindi. Murojaat raqami: #{id}\nJavob kelishi bilan sizga xabar beriladi.",
        "summary": "Yangi shaxsiy murojaat",
        "anonymous": False,
    },
    "proposal": {
        "db_type": "taklif",
        "title": "💡 <b>YANGI TAKLIF</b>",
        "ok": "✅ Taklifingiz qabul qilindi. Murojaat raqami: #{id}\nJavob kelishi bilan sizga xabar beriladi.",
        "summary": "Yangi taklif",
        "anonymous": False,
    },
}


async def submit_appeal(message: Message, state: FSMContext, kind: str):
    cfg = KINDS[kind]
    text = (message.caption or message.text or "").strip()
    file_id, file_type = None, None
    if message.photo:
        file_id, file_type = message.photo[-1].file_id, "photo"
    elif message.document:
        file_id, file_type = message.document.file_id, "document"

    if not text and not file_id:
        await message.answer("Iltimos, matn yozing yoki fayl yuboring.")
        return
    if len(text) > MAX_TEXT:
        await message.answer(f"Matn juda uzun (maksimum {MAX_TEXT} belgi). Qisqartirib qayta yuboring.")
        return

    user = None if cfg["anonymous"] else await get_user(message.from_user.id)
    appeal_id = await create_appeal(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=user["full_name"] if user else message.from_user.full_name,
        appeal_type=cfg["db_type"],
        text=text,
        file_id=file_id,
        file_type=file_type,
    )
    await state.clear()
    await message.answer(cfg["ok"].format(id=appeal_id), reply_markup=main_menu_kb(message.from_user.id))

    if user:
        who = (
            f"F.I.Sh: {esc(user['full_name'])}\nLavozim: {esc(user['position'])}\n"
            f"Bo'lim: {esc(user['department'])}\nTelefon: {esc(user['phone'])}"
        )
        brief = f"Yuboruvchi: {esc(user['full_name'])} ({esc(user['position'])}, {esc(user['department'])})"
    else:
        who = (
            f"Yuboruvchi ID: <code>{message.from_user.id}</code>\n"
            f"Username: @{esc(message.from_user.username) if message.from_user.username else 'mavjud emas'}"
        )
        brief = f"Yuboruvchi ID: {message.from_user.id}, username: @{esc(message.from_user.username) or 'mavjud emas'}"

    admin_text = f"{cfg['title']} #{appeal_id}\n\n{who}\n\nMatn: {esc(text) or '(matn kiritilmagan)'}"
    await dispatch_appeal(message.bot, appeal_id, admin_text, file_id, file_type, appeal_admin_kb(appeal_id))
    await audit.log(
        {"id": None, "name": f"tg:{message.from_user.id}", "role": None, "source": "bot", "ip": None},
        "appeal_created", "appeal", appeal_id, cfg["summary"],
    )
    await notify_superadmins(
        message.bot,
        f"ℹ️ {cfg['summary']} #{appeal_id}.\n{brief}\nTo'liq matn rahbar va yuristga yuborildi.",
    )
