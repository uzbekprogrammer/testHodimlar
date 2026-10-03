from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from keyboards.inline import ack_warning_kb
from keyboards.reply import cancel_kb
from handlers.appeal_common import submit_appeal
from utils.states import CorruptionStates
from utils.warnings_text import WARNING_RU, WARNING_UZ

router = Router()


@router.message(F.text == "🔴 Korrupsiya haqida xabar berish")
async def start_corruption(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(WARNING_UZ)
    await message.answer(WARNING_RU)
    await message.answer(
        "Davom etish uchun yuqoridagi ogohlantirish bilan tanishib chiqqaningizni tasdiqlang:",
        reply_markup=ack_warning_kb("corruption"),
    )


@router.callback_query(F.data == "ack_warning:corruption")
async def ack_corruption(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("✅ Tanishib chiqdingiz.")
    await state.set_state(CorruptionStates.waiting_text)
    await callback.message.answer(
        "Guvohi bo'lgan holatni batafsil yozib yuboring.\n"
        "Xohlasangiz rasm yoki hujjat ham biriktirishingiz mumkin.\n\n"
        "⚠️ Bu bo'limda ro'yxatdan o'tish talab qilinmaydi. "
        "Murojaatingiz korxona rahbari va yuristga yuboriladi.",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.message(CorruptionStates.waiting_text)
async def receive_corruption(message: Message, state: FSMContext):
    await submit_appeal(message, state, "corruption")
