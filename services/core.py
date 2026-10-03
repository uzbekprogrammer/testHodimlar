"""Бизнес-действия, общие для бота и сайта (одна реализация — одинаковое поведение + единая история действий)."""
import asyncio
import html
from datetime import date as date_cls

from aiogram.types import InlineKeyboardMarkup

from database import models
from database.db import fetchone
from services import audit
from utils import roles
from utils.notifications import notify_roles, notify_superadmins, safe_send
from utils.roles import ROLE_DIRECTOR, ROLE_LAWYER, ROLE_LABELS, ROLE_SECRETARY
from utils.working_days import format_date_label

MAX_REPLY = 3500


def esc(value) -> str:
    """HTML-экранирование пользовательского текста перед отправкой с parse_mode=HTML."""
    return html.escape("" if value is None else str(value))


async def dispatch_appeal(bot, appeal_id: int, admin_text: str, file_id=None, file_type=None,
                          keyboard: InlineKeyboardMarkup | None = None):
    """Полный текст обращения — руководителю и юристу (вместе с файлом, если есть)."""
    async def send(admin_id: int):
        try:
            caption_ok = len(admin_text) <= 1000
            if file_id and file_type == "photo":
                await bot.send_photo(admin_id, file_id, caption=admin_text if caption_ok else None)
            elif file_id and file_type == "document":
                await bot.send_document(admin_id, file_id, caption=admin_text if caption_ok else None)
            if not (file_id and caption_ok):
                await bot.send_message(admin_id, admin_text)
            if keyboard:
                await bot.send_message(admin_id, f"#{appeal_id} — ответить:", reply_markup=keyboard)
        except Exception:
            pass

    await asyncio.gather(*(send(i) for i in roles.ids_with_role(ROLE_DIRECTOR, ROLE_LAWYER)))


def can_answer(role: str | None) -> bool:
    return role in (ROLE_DIRECTOR, ROLE_LAWYER)


async def answer_appeal(bot, appeal_id: int, text: str, actor: dict) -> tuple[bool, str]:
    """Ответ на обращение: сохраняет, отправляет сотруднику в Telegram, уведомляет суперадминов, пишет в историю."""
    text = (text or "").strip()
    if not text:
        return False, "Введите текст ответа."
    if len(text) > MAX_REPLY:
        return False, f"Ответ слишком длинный (максимум {MAX_REPLY} символов)."
    if not can_answer(actor.get("role")):
        return False, "У вас нет права отвечать на обращения."
    appeal = await models.get_appeal(appeal_id)
    if not appeal:
        return False, "Обращение не найдено."

    label = ROLE_LABELS.get(actor["role"], actor["role"])
    await models.answer_appeal(appeal_id, text, label, actor.get("id"))
    await audit.log(actor, "appeal_answered", "appeal", appeal_id, f"Ответ: {text[:200]}")

    delivered = await safe_send(
        bot, appeal["telegram_id"],
        f"📩 Ответ на ваше обращение #{appeal_id} ({esc(label)}):\n\n{esc(text)}",
    )
    await notify_superadmins(bot, f"ℹ️ {esc(label)} ответил на обращение #{appeal_id}.")
    if actor["role"] == ROLE_LAWYER:
        await notify_roles(bot, f"ℹ️ Юрист ответил на обращение #{appeal_id}:\n\n{esc(text)}", ROLE_DIRECTOR)
    return True, "Ответ отправлен." if delivered else "Ответ сохранён, но сотрудник не получил сообщение (бот заблокирован?)."


async def decide_appointment(bot, appt_id: int, approve: bool, actor: dict) -> tuple[bool, str]:
    if actor.get("role") != ROLE_DIRECTOR:
        return False, "Решение по приёму принимает только руководитель."
    appt = await models.get_appointment(appt_id)
    if not appt:
        return False, "Запись не найдена."
    if appt["status"] != "kutilmoqda":
        return False, "По этой записи решение уже принято."

    status = "tasdiqlandi" if approve else "rad_etildi"
    await models.update_appointment_status(appt_id, status, decided_by=actor.get("name"))
    await audit.log(actor, "appointment_confirmed" if approve else "appointment_rejected", "appointment", appt_id)
    d = date_cls.fromisoformat(appt["appointment_date"])

    if approve:
        await safe_send(
            bot, appt["telegram_id"],
            f"✅ Ваша запись на приём к руководителю на {format_date_label(d)}, "
            f"{appt['appointment_time']} подтверждена.\n"
            f"✅ Sizning {format_date_label(d)} kuni soat {appt['appointment_time']} dagi "
            "direktor qabuliga yozilishingiz tasdiqlandi.",
        )
        await notify_roles(
            bot,
            f"📌 Подтверждённый приём #{appt_id}\n\n"
            f"Ф.И.О.: {esc(appt['full_name'])}\nТелефон: {esc(appt['phone'])}\n"
            f"Дата: {format_date_label(d)}\nВремя: {appt['appointment_time']}\nПричина: {esc(appt['reason'])}",
            ROLE_SECRETARY,
        )
        await notify_superadmins(bot, f"ℹ️ Руководитель подтвердил приём #{appt_id} и передал секретарю.")
    else:
        await safe_send(
            bot, appt["telegram_id"],
            "❌ К сожалению, запись на приём на выбранное время отклонена. Попробуйте выбрать другое время.\n"
            "❌ Afsuski, so'ragan vaqtingizga direktor qabuliga yozilish rad etildi. "
            "Iltimos, boshqa vaqtga qayta murojaat qiling.",
        )
        await notify_superadmins(bot, f"ℹ️ Руководитель отклонил приём #{appt_id}.")
    return True, "Приём подтверждён." if approve else "Приём отклонён."


async def broadcast(bot, text: str, actor: dict) -> tuple[int, int]:
    ids = await models.get_all_users()
    sem = asyncio.Semaphore(20)   # ~ в пределах лимитов Telegram (30 сообщений/сек)

    async def one(uid):
        async with sem:
            ok = await safe_send(bot, uid, text)
            await asyncio.sleep(0.05)
            return ok

    results = await asyncio.gather(*(one(u) for u in ids))
    sent = sum(1 for r in results if r)
    failed = len(results) - sent
    await audit.log(actor, "broadcast", details=f"Отправлено {sent}, не доставлено {failed}: {text[:200]}")
    await notify_superadmins(bot, f"ℹ️ {esc(actor.get('name'))} сделал рассылку: {sent} получателей.")
    return sent, failed


async def full_user_card(telegram_id: int) -> dict | None:
    return await fetchone("SELECT * FROM users WHERE telegram_id=?", (telegram_id,))
