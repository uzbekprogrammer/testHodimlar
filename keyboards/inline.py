from aiogram.utils.keyboard import InlineKeyboardBuilder

from utils.working_days import get_next_working_days, format_date_label, get_all_slots


def dates_kb():
    builder = InlineKeyboardBuilder()
    for d in get_next_working_days():
        builder.button(text=format_date_label(d), callback_data=f"date:{d.isoformat()}")
    builder.adjust(1)
    return builder.as_markup()


def times_kb(date_str: str, booked_slots: list):
    builder = InlineKeyboardBuilder()
    for slot in get_all_slots():
        if slot in booked_slots:
            continue
        builder.button(text=slot, callback_data=f"time:{date_str}:{slot}")
    builder.adjust(3)
    return builder.as_markup()


def ack_warning_kb(flow: str):
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Tanishib chiqdim / Ознакомился", callback_data=f"ack_warning:{flow}")
    return builder.as_markup()


def appeal_admin_kb(appeal_id: int):
    builder = InlineKeyboardBuilder()
    builder.button(text="💬 Javob yozish", callback_data=f"answer_appeal:{appeal_id}")
    return builder.as_markup()


def appointment_admin_kb(appointment_id: int):
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Tasdiqlash", callback_data=f"confirm_appt:{appointment_id}")
    builder.button(text="❌ Rad etish", callback_data=f"reject_appt:{appointment_id}")
    builder.adjust(2)
    return builder.as_markup()


def confirm_broadcast_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Yuborish", callback_data="broadcast:send")
    builder.button(text="❌ Bekor qilish", callback_data="broadcast:cancel")
    builder.adjust(2)
    return builder.as_markup()


def registration_confirm_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Tasdiqlash", callback_data="reg:confirm")
    builder.button(text="🔄 Qaytadan kiritish", callback_data="reg:restart")
    builder.button(text="❌ Bekor qilish", callback_data="reg:cancel")
    builder.adjust(1)
    return builder.as_markup()


def cleardb_confirm_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Ha, butunlay tozalash", callback_data="cleardb:confirm")
    builder.button(text="❌ Bekor qilish", callback_data="cleardb:cancel")
    builder.adjust(1)
    return builder.as_markup()
