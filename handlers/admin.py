"""Панель администратора в боте: статистика, обращения, приёмы, история действий, администраторы, рассылка."""
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import SUPERADMIN_SEE_APPEAL_TEXT
from database import models
from database.db import fetchall, scalar
from keyboards.inline import cleardb_confirm_kb, confirm_broadcast_kb
from keyboards.reply import ADMIN_BUTTON
from services import audit, stats
from services import admins as adm
from services.core import answer_appeal as answer_appeal_service, broadcast, can_answer, esc
from utils import roles
from utils.notifications import notify_superadmins, safe_send
from utils.roles import ROLE_LABELS, ROLE_SUPERADMIN
from utils.states import AdminStates
from utils.timefmt import fmt_ago, fmt_dt
from utils.working_days import format_date_label

router = Router()
PAGE = 8

TYPE_LABEL = {"corruption": "🔴 Коррупция", "personal": "👤 Личный вопрос", "taklif": "💡 Предложение"}
STATUS_LABEL = {"yangi": "🆕 новое", "v_rabote": "⏳ в работе", "javob_berildi": "✅ отвечено"}
APPT_LABEL = {"kutilmoqda": "⏳ ожидает", "tasdiqlandi": "✅ подтверждён", "rad_etildi": "❌ отклонён"}


async def _actor(user_id: int):
    admin = await adm.get_by_telegram(user_id)
    return admin, (audit.actor_from_admin(admin, "bot") if admin else None)


def _guard(user_id: int) -> bool:
    return roles.is_admin(user_id)


async def _show(target, text: str, kb: InlineKeyboardMarkup | None = None):
    """Редактирует сообщение панели; если нельзя — отправляет новое."""
    try:
        await target.edit_text(text, reply_markup=kb)
    except TelegramBadRequest as e:
        if "not modified" not in str(e):
            await target.answer(text, reply_markup=kb)


def _nav(builder: InlineKeyboardBuilder, prefix: str, page: int, total: int):
    pages = max(1, -(-total // PAGE))
    row = []
    if page > 0:
        row.append(("◀️", f"{prefix}:{page - 1}"))
    row.append((f"{page + 1}/{pages}", "ap:noop"))
    if page + 1 < pages:
        row.append(("▶️", f"{prefix}:{page + 1}"))
    for text, data in row:
        builder.button(text=text, callback_data=data)
    return len(row)


def home_kb(role: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📊 Статистика", callback_data="ap:stats")
    b.button(text="📨 Обращения", callback_data="ap:ap:new:0")
    b.button(text="📅 Приёмы", callback_data="ap:appt:0")
    b.button(text="📜 История действий", callback_data="ap:log:0")
    b.button(text="📢 Рассылка", callback_data="ap:bc")
    sizes = [2, 2, 1]
    if role == ROLE_SUPERADMIN:
        b.button(text="👥 Администраторы", callback_data="ap:adm:0")
        sizes = [2, 2, 1, 1]
    b.adjust(*sizes)
    return b.as_markup()


def back_kb(to: str = "ap:home") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="⬅️ Назад", callback_data=to)
    return b.as_markup()


# ---------------------- вход ----------------------

@router.message(Command("admin"))
@router.message(F.text == ADMIN_BUTTON)
async def open_panel(message: Message, state: FSMContext):
    if not _guard(message.from_user.id):
        return
    await state.clear()
    role = roles.role_of(message.from_user.id)
    await message.answer(
        f"🛠 <b>Панель администратора</b>\nToshkent EM · Обращение бот\nВаша роль: <b>{ROLE_LABELS[role]}</b>",
        reply_markup=home_kb(role),
    )


@router.callback_query(F.data == "ap:home")
async def panel_home(callback: CallbackQuery, state: FSMContext):
    if not _guard(callback.from_user.id):
        return await callback.answer()
    await state.clear()
    role = roles.role_of(callback.from_user.id)
    await _show(callback.message, f"🛠 <b>Панель администратора</b>\nВаша роль: <b>{ROLE_LABELS[role]}</b>", home_kb(role))
    await callback.answer()


@router.callback_query(F.data == "ap:noop")
async def noop(callback: CallbackQuery):
    await callback.answer()


# ---------------------- статистика / мониторинг ----------------------

@router.callback_query(F.data == "ap:stats")
async def panel_stats(callback: CallbackQuery):
    if not _guard(callback.from_user.id):
        return await callback.answer()
    o = await stats.overview()
    m = await stats.monitoring()
    sla = m["sla"]
    text = (
        "📊 <b>Статистика и мониторинг</b>\n\n"
        f"Обращений всего: <b>{o['total']}</b> (сегодня: {o['today']})\n"
        f"  🆕 новых: {o['new']} · ⏳ в работе: {o['in_work']} · ✅ отвечено: {o['answered']}\n"
        f"  🔴 коррупция: {o['corruption']} · 👤 личные: {o['personal']} · 💡 предложения: {o['proposal']}\n"
        f"Среднее время ответа: <b>{o['avg_hours']} ч</b>\n\n"
        f"⏱ Без ответа: &lt;4ч — {sla['fresh']}, 4–24ч — {sla['warn']}, "
        f"<b>просрочено (&gt;24ч) — {sla['overdue']}</b>\n\n"
        f"📅 Приёмы: ожидают решения — {o['appt_pending']}, предстоящих — {o['appt_upcoming']}\n"
        f"👥 Сотрудников в базе: {o['users']}\n"
        f"🌐 Сайт: сессий {m['sessions']}, неудачных входов за 24ч: {m['failed_logins_24h']}"
    )
    b = InlineKeyboardBuilder()
    b.button(text="🔄 Обновить", callback_data="ap:stats")
    b.button(text="⬅️ Назад", callback_data="ap:home")
    b.adjust(2)
    stats.invalidate()
    await _show(callback.message, text, b.as_markup())
    await callback.answer()


# ---------------------- обращения ----------------------

@router.callback_query(F.data.startswith("ap:ap:"))
async def panel_appeals(callback: CallbackQuery):
    if not _guard(callback.from_user.id):
        return await callback.answer()
    _, _, flt, page = callback.data.split(":")
    page = int(page)
    where = "WHERE status!='javob_berildi'" if flt == "new" else ""
    total = await scalar(f"SELECT COUNT(*) FROM appeals {where}")
    rows = await fetchall(
        f"SELECT id, appeal_type, status, full_name, created_at FROM appeals {where} ORDER BY id DESC LIMIT ? OFFSET ?",
        (PAGE, page * PAGE),
    )
    b = InlineKeyboardBuilder()
    for r in rows:
        b.button(
            text=f"#{r['id']} {TYPE_LABEL.get(r['appeal_type'], r['appeal_type'])} · {fmt_ago(r['created_at'])}",
            callback_data=f"ap:view:{r['id']}",
        )
    b.adjust(1)
    nav = _nav(b, f"ap:ap:{flt}", page, total)
    b.button(text="Все" if flt == "new" else "Только без ответа", callback_data=f"ap:ap:{'all' if flt == 'new' else 'new'}:0")
    b.button(text="⬅️ Назад", callback_data="ap:home")
    b.adjust(*([1] * len(rows)), nav, 2)
    title = "без ответа" if flt == "new" else "все"
    await _show(callback.message, f"📨 <b>Обращения ({title})</b> — всего {total}", b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("ap:view:"))
async def panel_appeal_view(callback: CallbackQuery):
    if not _guard(callback.from_user.id):
        return await callback.answer()
    appeal = await models.get_appeal(int(callback.data.split(":")[2]))
    if not appeal:
        return await callback.answer("Обращение не найдено.", show_alert=True)
    role = roles.role_of(callback.from_user.id)
    hide = role == ROLE_SUPERADMIN and not SUPERADMIN_SEE_APPEAL_TEXT
    body = "🔒 (текст доступен руководителю и юристу)" if hide else esc(appeal["text"]) or "—"
    text = (
        f"{TYPE_LABEL.get(appeal['appeal_type'], appeal['appeal_type'])} <b>#{appeal['id']}</b>\n"
        f"Статус: {STATUS_LABEL.get(appeal['status'], appeal['status'])}\n"
        f"Создано: {fmt_dt(appeal['created_at'])}\n"
        + (f"От: {esc(appeal['full_name'])}\n" if appeal["appeal_type"] != "corruption" else "")
        + f"\n{body}\n"
        + (f"\n📩 Ответ ({esc(appeal['answered_by'])}, {fmt_dt(appeal['answered_at'])}):\n{esc(appeal['admin_comment'])}" if appeal["admin_comment"] else "")
    )
    b = InlineKeyboardBuilder()
    if can_answer(role) and appeal["status"] != "javob_berildi":
        b.button(text="💬 Ответить", callback_data=f"answer_appeal:{appeal['id']}")
    if appeal["status"] == "yangi" and role != "secretary":
        b.button(text="⏳ Взять в работу", callback_data=f"ap:work:{appeal['id']}")
    b.button(text="⬅️ К списку", callback_data="ap:ap:new:0")
    b.adjust(1)
    await _show(callback.message, text, b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("ap:work:"))
async def panel_take_work(callback: CallbackQuery):
    admin, actor = await _actor(callback.from_user.id)
    if not admin or admin["role"] == "secretary":
        return await callback.answer("Нет доступа.", show_alert=True)
    appeal_id = int(callback.data.split(":")[2])
    await models.set_appeal_status(appeal_id, "v_rabote")
    await audit.log(actor, "appeal_status", "appeal", appeal_id, "В работе")
    await callback.answer("Взято в работу")
    callback.data = f"ap:view:{appeal_id}"
    await panel_appeal_view(callback)


@router.callback_query(F.data.startswith("answer_appeal:"))
async def start_answer(callback: CallbackQuery, state: FSMContext):
    admin, _ = await _actor(callback.from_user.id)
    if not admin or not can_answer(admin["role"]):
        return await callback.answer("У вас нет права отвечать на обращения.", show_alert=True)
    appeal_id = int(callback.data.split(":")[1])
    if not await models.get_appeal(appeal_id):
        return await callback.answer("Обращение не найдено.", show_alert=True)
    await state.update_data(appeal_id=appeal_id)
    await state.set_state(AdminStates.waiting_comment)
    await callback.message.answer(f"Напишите ответ на обращение #{appeal_id}:\n(для отмены: /admin)")
    await callback.answer()


@router.message(AdminStates.waiting_comment, F.text)
async def receive_answer(message: Message, state: FSMContext):
    if message.text.startswith("/"):
        await state.clear()
        return await message.answer("Отменено.")
    admin, actor = await _actor(message.from_user.id)
    if not admin:
        return
    data = await state.get_data()
    ok, msg = await answer_appeal_service(message.bot, data["appeal_id"], message.text, actor)
    if ok:
        await state.clear()
    await message.answer(("✅ " if ok else "⚠️ ") + msg)


# ---------------------- приёмы ----------------------

@router.callback_query(F.data.startswith("ap:appt:"))
async def panel_appts(callback: CallbackQuery):
    if not _guard(callback.from_user.id):
        return await callback.answer()
    page = int(callback.data.split(":")[2])
    total = await scalar("SELECT COUNT(*) FROM appointments WHERE status='kutilmoqda'")
    rows = await fetchall(
        "SELECT * FROM appointments WHERE status='kutilmoqda' ORDER BY appointment_date, appointment_time LIMIT ? OFFSET ?",
        (PAGE, page * PAGE),
    )
    is_dir = roles.is_director(callback.from_user.id)
    lines = [f"📅 <b>Приёмы, ожидающие решения</b> — {total}\n"]
    for r in rows:
        from datetime import date as d_cls
        lines.append(
            f"<b>#{r['id']}</b> {format_date_label(d_cls.fromisoformat(r['appointment_date']))} {r['appointment_time']}\n"
            f"{esc(r['full_name'])}, {esc(r['phone'])}\nПричина: {esc(r['reason'])}\n"
        )
    b = InlineKeyboardBuilder()
    if is_dir:
        for r in rows:
            b.button(text=f"✅ #{r['id']}", callback_data=f"confirm_appt:{r['id']}")
            b.button(text=f"❌ #{r['id']}", callback_data=f"reject_appt:{r['id']}")
        b.adjust(2)
    nav = _nav(b, "ap:appt", page, total)
    b.button(text="⬅️ Назад", callback_data="ap:home")
    b.adjust(*([2] * len(rows) if is_dir else []), nav, 1)
    await _show(callback.message, "\n".join(lines) if rows else "📅 Нет записей, ожидающих решения.", b.as_markup())
    await callback.answer()


# ---------------------- история действий ----------------------

@router.callback_query(F.data.startswith("ap:log:"))
async def panel_log(callback: CallbackQuery):
    if not _guard(callback.from_user.id):
        return await callback.answer()
    if roles.is_secretary(callback.from_user.id):
        return await callback.answer("Нет доступа.", show_alert=True)
    page = int(callback.data.split(":")[2])
    rows, total = await audit.search(limit=10, offset=page * 10)
    lines = [f"📜 <b>История действий</b> — {total}\n"]
    for r in rows:
        src = {"bot": "🤖", "web": "🌐"}.get(r["source"], "⚙️")
        lines.append(
            f"{src} <code>{fmt_dt(r['ts'])}</code> · {esc(r['actor_name'])}\n"
            f"   {audit.ACTION_LABELS.get(r['action'], r['action'])}"
            + (f" #{esc(r['entity_id'])}" if r["entity_id"] else "")
        )
    b = InlineKeyboardBuilder()
    nav = _nav(b, "ap:log", page, total)
    b.button(text="⬅️ Назад", callback_data="ap:home")
    b.adjust(nav, 1)
    await _show(callback.message, "\n".join(lines), b.as_markup())
    await callback.answer()


# ---------------------- администраторы (только superadmin) ----------------------

def _only_super(callback: CallbackQuery) -> bool:
    return roles.is_superadmin(callback.from_user.id)


@router.callback_query(F.data.startswith("ap:adm:") & ~F.data.startswith("ap:adm:v:"))
async def panel_admins(callback: CallbackQuery, state: FSMContext):
    if not _only_super(callback):
        return await callback.answer("Только для суперадминистратора.", show_alert=True)
    await state.clear()
    page = int(callback.data.split(":")[2])
    items = await adm.list_admins()
    b = InlineKeyboardBuilder()
    for a in items[page * PAGE:(page + 1) * PAGE]:
        mark = "" if a["is_active"] else "🚫 "
        b.button(text=f"{mark}{a['full_name']} — {ROLE_LABELS[a['role']]}", callback_data=f"ap:adm:v:{a['id']}")
    b.adjust(1)
    nav = _nav(b, "ap:adm", page, len(items))
    b.button(text="➕ Добавить администратора", callback_data="ap:addadm")
    b.button(text="⬅️ Назад", callback_data="ap:home")
    b.adjust(*([1] * len(items[page * PAGE:(page + 1) * PAGE])), nav, 1, 1)
    await _show(callback.message, f"👥 <b>Администраторы</b> — {len(items)}", b.as_markup())
    await callback.answer()


def _admin_card(a: dict) -> str:
    return (
        f"👤 <b>{esc(a['full_name'])}</b>\nРоль: {ROLE_LABELS[a['role']]}\n"
        f"Telegram ID: <code>{a['telegram_id'] or '—'}</code>\n"
        f"Логин на сайте: <code>{esc(a['username']) if a['username'] else '—'}</code>\n"
        f"Статус: {'активен' if a['is_active'] else '🚫 отключён'}\n"
        f"Последний вход на сайт: {fmt_dt(a['last_login'])}"
    )


def _admin_kb(a: dict) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for r, label in ROLE_LABELS.items():
        if r != a["role"]:
            b.button(text=f"Роль → {label}", callback_data=f"ap:role:{a['id']}:{r}")
    b.button(text="🔑 Доступ на сайт / сбросить пароль", callback_data=f"ap:webpw:{a['id']}")
    b.button(text="🚫 Отключить" if a["is_active"] else "✅ Включить", callback_data=f"ap:toggle:{a['id']}")
    b.button(text="🗑 Удалить", callback_data=f"ap:del:{a['id']}")
    b.button(text="⬅️ Назад", callback_data="ap:adm:0")
    b.adjust(1)
    return b.as_markup()


@router.callback_query(F.data.startswith("ap:adm:v:"))
async def panel_admin_view(callback: CallbackQuery):
    if not _only_super(callback):
        return await callback.answer("Только для суперадминистратора.", show_alert=True)
    a = await adm.get_by_id(int(callback.data.split(":")[3]))
    if not a:
        return await callback.answer("Не найден.", show_alert=True)
    await _show(callback.message, _admin_card(a), _admin_kb(a))
    await callback.answer()


async def _admin_action(callback: CallbackQuery, action: str, **fields):
    """Общая обёртка: проверка прав, защита последнего суперадмина, запись в историю."""
    if not _only_super(callback):
        await callback.answer("Только для суперадминистратора.", show_alert=True)
        return None
    _, actor = await _actor(callback.from_user.id)
    return actor


@router.callback_query(F.data.startswith("ap:role:"))
async def change_role(callback: CallbackQuery):
    actor = await _admin_action(callback, "admin_updated")
    if not actor:
        return
    _, _, aid, new_role = callback.data.split(":")
    a = await adm.get_by_id(int(aid))
    if not a or new_role not in adm.VALID_ROLES:
        return await callback.answer("Ошибка.", show_alert=True)
    if a["role"] == ROLE_SUPERADMIN and await adm.active_superadmin_count(a["id"]) == 0:
        return await callback.answer("Нельзя понизить последнего суперадминистратора.", show_alert=True)
    await adm.update_admin(a["id"], role=new_role)
    await audit.log(actor, "admin_updated", "admin", a["id"], f"Роль: {a['role']} → {new_role}")
    await callback.answer("Роль изменена")
    await _show(callback.message, _admin_card(await adm.get_by_id(a["id"])), _admin_kb(await adm.get_by_id(a["id"])))


@router.callback_query(F.data.startswith("ap:toggle:"))
async def toggle_admin(callback: CallbackQuery):
    actor = await _admin_action(callback, "admin_updated")
    if not actor:
        return
    a = await adm.get_by_id(int(callback.data.split(":")[2]))
    if not a:
        return await callback.answer("Не найден.", show_alert=True)
    if a["is_active"] and a["role"] == ROLE_SUPERADMIN and await adm.active_superadmin_count(a["id"]) == 0:
        return await callback.answer("Нельзя отключить последнего суперадминистратора.", show_alert=True)
    await adm.update_admin(a["id"], is_active=0 if a["is_active"] else 1)
    await audit.log(actor, "admin_updated", "admin", a["id"], "Отключён" if a["is_active"] else "Включён")
    fresh = await adm.get_by_id(a["id"])
    await _show(callback.message, _admin_card(fresh), _admin_kb(fresh))
    await callback.answer("Готово")


@router.callback_query(F.data.startswith("ap:del:"))
async def delete_admin(callback: CallbackQuery):
    actor = await _admin_action(callback, "admin_removed")
    if not actor:
        return
    a = await adm.get_by_id(int(callback.data.split(":")[2]))
    if not a:
        return await callback.answer("Не найден.", show_alert=True)
    if a["role"] == ROLE_SUPERADMIN and await adm.active_superadmin_count(a["id"]) == 0:
        return await callback.answer("Нельзя удалить последнего суперадминистратора.", show_alert=True)
    await adm.delete_admin(a["id"])
    await audit.log(actor, "admin_removed", "admin", a["id"], a["full_name"])
    await callback.answer("Удалён")
    await _show(callback.message, "🗑 Администратор удалён.", back_kb("ap:adm:0"))


@router.callback_query(F.data.startswith("ap:webpw:"))
async def web_access(callback: CallbackQuery):
    actor = await _admin_action(callback, "admin_password_reset")
    if not actor:
        return
    a = await adm.get_by_id(int(callback.data.split(":")[2]))
    if not a:
        return await callback.answer("Не найден.", show_alert=True)
    username = a["username"] or f"user{a['id']}"
    password = adm.generate_password()
    if not a["username"]:
        await adm.update_admin(a["id"], username=username)
    await adm.set_password(a["id"], password, must_change=True)
    await audit.log(actor, "admin_password_reset", "admin", a["id"], f"Логин: {username}")
    await callback.message.answer(
        f"🔑 Доступ на сайт для <b>{esc(a['full_name'])}</b>\n\nЛогин: <code>{esc(username)}</code>\n"
        f"Пароль: <code>{password}</code>\n\nПароль показан один раз — передайте его сотруднику; "
        "при первом входе система попросит сменить пароль. Удалите это сообщение после передачи."
    )
    await callback.answer()


@router.callback_query(F.data == "ap:addadm")
async def add_admin_start(callback: CallbackQuery, state: FSMContext):
    if not _only_super(callback):
        return await callback.answer("Только для суперадминистратора.", show_alert=True)
    await state.set_state(AdminStates.waiting_new_admin_id)
    await callback.message.answer(
        "Отправьте Telegram ID нового администратора (число) или перешлите сюда любое его сообщение.\n"
        "Для отмены: /admin"
    )
    await callback.answer()


@router.message(AdminStates.waiting_new_admin_id)
async def add_admin_id(message: Message, state: FSMContext):
    if not roles.is_superadmin(message.from_user.id):
        return
    tg_id = None
    if message.forward_from:
        tg_id = message.forward_from.id
    elif message.text and message.text.strip().lstrip("-").isdigit():
        tg_id = int(message.text.strip())
    if not tg_id or tg_id <= 0:
        return await message.answer("Нужен числовой Telegram ID или пересланное сообщение. Повторите или /admin для отмены.")
    if await adm.get_by_telegram(tg_id) or await scalar("SELECT 1 FROM admins WHERE telegram_id=?", (tg_id,)):
        return await message.answer("Этот пользователь уже есть в списке администраторов.")
    await state.update_data(new_tg=tg_id)
    await state.set_state(AdminStates.waiting_new_admin_name)
    await message.answer("Введите имя (Ф.И.О.) администратора:")


@router.message(AdminStates.waiting_new_admin_name, F.text)
async def add_admin_name(message: Message, state: FSMContext):
    if not roles.is_superadmin(message.from_user.id):
        return
    name = message.text.strip()
    if not 2 <= len(name) <= 80 or name.startswith("/"):
        return await message.answer("Имя должно быть от 2 до 80 символов.")
    await state.update_data(new_name=name)
    b = InlineKeyboardBuilder()
    for r, label in ROLE_LABELS.items():
        b.button(text=label, callback_data=f"ap:newrole:{r}")
    b.adjust(1)
    await message.answer("Выберите роль:", reply_markup=b.as_markup())


@router.callback_query(F.data.startswith("ap:newrole:"))
async def add_admin_role(callback: CallbackQuery, state: FSMContext):
    if not _only_super(callback):
        return await callback.answer()
    data = await state.get_data()
    role = callback.data.split(":")[2]
    if "new_tg" not in data or role not in adm.VALID_ROLES:
        return await callback.answer("Сессия устарела, начните заново: /admin", show_alert=True)
    aid = await adm.create_admin(data["new_name"], role, telegram_id=data["new_tg"])
    await state.clear()
    _, actor = await _actor(callback.from_user.id)
    await audit.log(actor, "admin_added", "admin", aid, f"{data['new_name']} ({role}), tg {data['new_tg']}")
    await _show(callback.message, f"✅ Администратор <b>{esc(data['new_name'])}</b> добавлен ({ROLE_LABELS[role]}).", back_kb("ap:adm:0"))
    await callback.answer()
    await safe_send(callback.bot, data["new_tg"], f"Вам выдана роль «{ROLE_LABELS[role]}» в боте. Откройте /admin.")


# ---------------------- рассылка ----------------------

@router.callback_query(F.data == "ap:bc")
async def panel_broadcast(callback: CallbackQuery, state: FSMContext):
    if not _guard(callback.from_user.id):
        return await callback.answer()
    await state.set_state(AdminStates.waiting_broadcast)
    await callback.message.answer("Введите текст рассылки для всех сотрудников (отмена: /admin):")
    await callback.answer()


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, state: FSMContext):
    if not _guard(message.from_user.id):
        return
    await state.set_state(AdminStates.waiting_broadcast)
    await message.answer("Введите текст рассылки для всех сотрудников:")


@router.message(AdminStates.waiting_broadcast, F.text)
async def receive_broadcast_text(message: Message, state: FSMContext):
    if not _guard(message.from_user.id):
        return
    if message.text.startswith("/"):
        await state.clear()
        return await message.answer("Отменено.")
    await state.update_data(broadcast_text=message.text)
    await message.answer(f"Отправить всем сотрудникам?\n\n{esc(message.text)}", reply_markup=confirm_broadcast_kb())


@router.callback_query(F.data == "broadcast:send")
async def send_broadcast(callback: CallbackQuery, state: FSMContext):
    admin, actor = await _actor(callback.from_user.id)
    if not admin:
        return await callback.answer()
    data = await state.get_data()
    text = data.get("broadcast_text")
    await state.clear()
    if not text:
        return await callback.answer()
    await callback.message.edit_text("⏳ Отправляю…")
    sent, failed = await broadcast(callback.bot, esc(text), actor)
    await callback.message.edit_text(f"✅ Доставлено: {sent}\n❌ Не доставлено: {failed}")
    await callback.answer()


@router.callback_query(F.data == "broadcast:cancel")
async def cancel_broadcast(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Отменено.")
    await callback.answer()


# ---------------------- очистка базы (только superadmin) ----------------------

@router.message(Command("cleardb"))
async def cmd_cleardb(message: Message):
    if not roles.is_superadmin(message.from_user.id):
        return
    await message.answer(
        "⚠️ <b>ВНИМАНИЕ!</b>\n\nКоманда безвозвратно удалит ВСЕХ сотрудников, обращения и записи на приём "
        "(администраторы и история действий сохраняются).\n\nПродолжить?",
        reply_markup=cleardb_confirm_kb(),
    )


@router.callback_query(F.data == "cleardb:confirm")
async def confirm_cleardb(callback: CallbackQuery):
    if not roles.is_superadmin(callback.from_user.id):
        return await callback.answer("Нет доступа.", show_alert=True)
    _, actor = await _actor(callback.from_user.id)
    await models.clear_all_data()
    await audit.log(actor, "cleardb")
    await callback.message.edit_text("✅ База данных очищена.")
    await callback.answer("Готово")
    await notify_superadmins(callback.bot, f"ℹ️ {esc(callback.from_user.full_name)} очистил базу данных.")


@router.callback_query(F.data == "cleardb:cancel")
async def cancel_cleardb(callback: CallbackQuery):
    await callback.message.edit_text("Отменено. База не изменена.")
    await callback.answer()


# ---------------------- /to_director ----------------------

@router.message(Command("to_director"))
async def forward_reply_to_director(message: Message):
    """Суперадмин отвечает командой на сообщение — оно пересылается руководителю(ям)."""
    if not roles.is_superadmin(message.from_user.id):
        return
    if not message.reply_to_message:
        return await message.reply("Используйте команду как ответ (reply) на нужное сообщение.")
    for uid in roles.ids_with_role(roles.ROLE_DIRECTOR):
        try:
            await message.bot.forward_message(uid, message.chat.id, message.reply_to_message.message_id)
        except Exception:
            pass
    await message.reply("✅ Отправлено руководителю.")
