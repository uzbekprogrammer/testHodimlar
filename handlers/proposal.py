from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from database.models import get_user
from handlers.registration import begin_registration
from keyboards.inline import ack_warning_kb
from keyboards.reply import cancel_kb
from handlers.appeal_common import submit_appeal
from utils.states import ProposalStates
from utils.warnings_text import WARNING_RU, WARNING_UZ

router = Router()


@router.message(F.text == "💡 Taklif bildirish")
async def start_proposal(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(WARNING_UZ)
    await message.answer(WARNING_RU)
    await message.answer(
        "Davom etish uchun yuqoridagi ogohlantirish bilan tanishib chiqqaningizni tasdiqlang:",
        reply_markup=ack_warning_kb("proposal"),
    )


@router.callback_query(F.data == "ack_warning:proposal")
async def ack_proposal(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("✅ Tanishib chiqdingiz.")

    user = await get_user(callback.from_user.id)
    if user:
        await state.set_state(ProposalStates.waiting_appeal_text)
        await callback.message.answer(
            "Taklifingizni batafsil yozib yuboring:",
            reply_markup=cancel_kb(),
        )
    else:
        await callback.message.answer(
            "Bu bo'limda murojaat qilish uchun avval ro'yxatdan o'tishingiz kerak."
        )
        await begin_registration(callback.message, state, "proposal_appeal")
    await callback.answer()


@router.message(ProposalStates.waiting_appeal_text)
async def receive_proposal(message: Message, state: FSMContext):
    await submit_appeal(message, state, "proposal")
