from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from keyboards.reply import main_menu_kb
from services.core import esc

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        f"Assalomu alaykum, <b>{esc(message.from_user.full_name)}</b>!\n\n"
        "Toshkent EM — «Обращение бот»: xodimlarning murojaat botiga xush kelibsiz.\n"
        "Quyidagi bo'limlardan birini tanlang:",
        reply_markup=main_menu_kb(message.from_user.id),
    )


@router.message(F.text == "❌ Bekor qilish")
async def cancel_handler(message: Message, state: FSMContext):
    """Har qanday holatda (state) ishlaydigan umumiy bekor qilish tugmasi.
    Shu fayl birinchi router bo'lib ro'yxatdan o'tgani uchun (main.py da),
    boshqa bo'limlardagi maxsus handlerlardan oldin ishga tushadi."""
    current = await state.get_state()
    if current is None:
        return
    await state.clear()
    await message.answer("Bekor qilindi.", reply_markup=main_menu_kb(message.from_user.id))
