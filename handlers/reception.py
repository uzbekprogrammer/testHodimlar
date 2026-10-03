from datetime import date as date_cls

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from database.models import create_appointment, get_booked_slots, get_user
from handlers.registration import begin_registration
from keyboards.inline import appointment_admin_kb, dates_kb, times_kb
from keyboards.reply import cancel_kb, main_menu_kb
from services import audit
from services.admins import get_by_telegram
from services.core import decide_appointment, esc
from utils.notifications import notify_roles, notify_superadmins
from utils.roles import ROLE_DIRECTOR
from utils.states import ReceptionStates
from utils.working_days import format_date_label

router = Router()


@router.message(F.text == "📅 Rahbar qabuliga yozilish")
async def start_reception(message: Message, state: FSMContext):
    user = await get_user(message.from_user.id)
    if user:
        await state.update_data(full_name=user["full_name"], phone=user["phone"])
        await state.set_state(ReceptionStates.choosing_date)
        await message.answer("Qaysi kunga yozilmoqchisiz?", reply_markup=dates_kb())
    else:
        await message.answer(
            "Qabulga yozilish uchun avval ro'yxatdan o'tishingiz kerak."
        )
        await begin_registration(message, state, "reception_booking")


@router.callback_query(ReceptionStates.choosing_date, F.data.startswith("date:"))
async def choose_date(callback: CallbackQuery, state: FSMContext):
    date_str = callback.data.split(":", 1)[1]
    booked = await get_booked_slots(date_str)
    await state.update_data(date=date_str)
    await state.set_state(ReceptionStates.choosing_time)

    d = date_cls.fromisoformat(date_str)
    all_slots_taken = len(booked) >= 7  # 8 soatdan tushlik chiqib 7 ta slot bor
    if all_slots_taken:
        await callback.answer("Bu kunda bo'sh vaqt qolmagan, boshqa kunni tanlang.", show_alert=True)
        return

    await callback.message.edit_text(
        f"{format_date_label(d)} kuni uchun bo'sh vaqtni tanlang:",
        reply_markup=times_kb(date_str, booked),
    )
    await callback.answer()


@router.callback_query(ReceptionStates.choosing_time, F.data.startswith("time:"))
async def choose_time(callback: CallbackQuery, state: FSMContext):
    _, date_str, time_str = callback.data.split(":", 2)
    await state.update_data(time=time_str)
    await state.set_state(ReceptionStates.waiting_reason)

    await callback.message.edit_text(f"Tanlangan vaqt: {date_str} {time_str}")
    await callback.message.answer(
        "Qabulga yozilish sababini qisqacha yozing:",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.message(ReceptionStates.waiting_reason)
async def get_reason(message: Message, state: FSMContext):
    reason = (message.text or "").strip()
    if not 3 <= len(reason) <= 500:
        await message.answer("Iltimos, sababni matn bilan yozing (3–500 belgi).")
        return
    data = await state.get_data()
    if data["time"] in await get_booked_slots(data["date"]):
        await state.set_state(ReceptionStates.choosing_date)
        await message.answer(
            "Afsuski, bu vaqt hozirgina band qilindi. Iltimos, boshqa vaqtni tanlang:", reply_markup=dates_kb()
        )
        return
    appointment_id = await create_appointment(
        telegram_id=message.from_user.id,
        full_name=data["full_name"],
        phone=data["phone"],
        reason=reason,
        date=data["date"],
        time=data["time"],
    )
    await state.clear()

    d = date_cls.fromisoformat(data["date"])
    await message.answer(
        "✅ So'rovingiz yuborildi!\n\n"
        f"📅 Sana: {format_date_label(d)}\n"
        f"🕐 Vaqt: {data['time']}\n\n"
        "Direktor tasdiqlashi bilan sizga xabar beriladi.",
        reply_markup=main_menu_kb(message.from_user.id),
    )

    admin_text = (
        f"📅 <b>YANGI QABULGA YOZILISH SO'ROVI</b> #{appointment_id}\n\n"
        f"F.I.Sh: {esc(data['full_name'])}\n"
        f"Telefon: {esc(data['phone'])}\n"
        f"Sana: {format_date_label(d)}\n"
        f"Vaqt: {data['time']}\n"
        f"Sabab: {esc(reason)}"
    )
    await notify_roles(message.bot, admin_text, ROLE_DIRECTOR, reply_markup=appointment_admin_kb(appointment_id))
    await notify_superadmins(message.bot, admin_text)
    await audit.log(
        {"id": None, "name": data["full_name"], "role": None, "source": "bot", "ip": None},
        "appointment_created", "appointment", appointment_id, f"{data['date']} {data['time']}",
    )


@router.callback_query(F.data.startswith("confirm_appt:"))
async def confirm_appointment(callback: CallbackQuery):
    await _decide(callback, True)


@router.callback_query(F.data.startswith("reject_appt:"))
async def reject_appointment(callback: CallbackQuery):
    await _decide(callback, False)


async def _decide(callback: CallbackQuery, approve: bool):
    admin = await get_by_telegram(callback.from_user.id)
    if not admin or admin["role"] != ROLE_DIRECTOR:
        await callback.answer("Это действие доступно только руководителю.", show_alert=True)
        return
    appointment_id = int(callback.data.split(":")[1])
    ok, msg = await decide_appointment(callback.bot, appointment_id, approve, audit.actor_from_admin(admin, "bot"))
    if ok:
        await callback.message.edit_text(callback.message.html_text + ("\n\n✅ ПОДТВЕРЖДЕНО" if approve else "\n\n❌ ОТКЛОНЕНО"))
    await callback.answer(msg, show_alert=not ok)
