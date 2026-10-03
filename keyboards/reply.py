from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

from utils.roles import is_admin


ADMIN_BUTTON = "🛠 Панель администратора"


def main_menu_kb(user_id: int | None = None) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="🔴 Korrupsiya haqida xabar berish")],
        [KeyboardButton(text="👤 Shaxsiy masala bo'yicha murojaat")],
        [KeyboardButton(text="💡 Taklif bildirish")],
        [KeyboardButton(text="📅 Rahbar qabuliga yozilish")],
        [KeyboardButton(text="✏️ Ma'lumotlarimni tahrirlash")],
    ]
    if user_id is not None and is_admin(user_id):
        rows.append([KeyboardButton(text=ADMIN_BUTTON)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def phone_request_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Raqamni ulashish", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Bekor qilish")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


remove_kb = ReplyKeyboardRemove()
