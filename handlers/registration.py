from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from database.models import create_user
from keyboards.inline import dates_kb, registration_confirm_kb
from keyboards.reply import cancel_kb, main_menu_kb, phone_request_kb
from services import audit
from services.core import esc
from utils.states import PersonalStates, ProposalStates, ReceptionStates, RegistrationStates

router = Router()


def _valid_text(value) -> bool:
    return isinstance(value, str) and 2 <= len(value.strip()) <= 120


async def begin_registration(message: Message, state: FSMContext, next_action: str):
    """Ro'yxatdan o'tish / tahrirlash jarayonini boshlaydi.

    next_action - ma'lumotlar tasdiqlangach qaysi bo'limga qaytish kerakligini bildiradi:
    'personal_appeal', 'proposal_appeal', 'reception_booking' yoki 'profile_edit'.
    """
    await state.set_data({"next_action": next_action})
    await state.set_state(RegistrationStates.waiting_fullname)
    await message.answer("F.I.Sh ni to'liq kiriting:", reply_markup=cancel_kb())


@router.message(F.text == "✏️ Ma'lumotlarimni tahrirlash")
async def edit_profile(message: Message, state: FSMContext):
    await begin_registration(message, state, "profile_edit")


@router.message(RegistrationStates.waiting_fullname)
async def get_fullname(message: Message, state: FSMContext):
    if not _valid_text(message.text):
        await message.answer("Iltimos, matn ko'rinishida kiriting (2–120 belgi).")
        return
    await state.update_data(full_name=message.text.strip())
    await state.set_state(RegistrationStates.waiting_position)
    await message.answer("Lavozimingizni kiriting:")


@router.message(RegistrationStates.waiting_position)
async def get_position(message: Message, state: FSMContext):
    if not _valid_text(message.text):
        await message.answer("Iltimos, matn ko'rinishida kiriting (2–120 belgi).")
        return
    await state.update_data(position=message.text.strip())
    await state.set_state(RegistrationStates.waiting_department)
    await message.answer("Bo'lim / sexingizni kiriting:")


@router.message(RegistrationStates.waiting_department)
async def get_department(message: Message, state: FSMContext):
    if not _valid_text(message.text):
        await message.answer("Iltimos, matn ko'rinishida kiriting (2–120 belgi).")
        return
    await state.update_data(department=message.text.strip())
    await state.set_state(RegistrationStates.waiting_phone)
    await message.answer(
        "Telefon raqamingizni tasdiqlash uchun tugmani bosing:",
        reply_markup=phone_request_kb(),
    )


@router.message(RegistrationStates.waiting_phone, F.contact)
async def get_phone(message: Message, state: FSMContext):
    if message.contact.user_id != message.from_user.id:
        await message.answer("Iltimos, faqat o'zingizning raqamingizni ulashing.")
        return

    await state.update_data(phone=message.contact.phone_number)
    await state.set_state(RegistrationStates.confirming)
    data = await state.get_data()

    summary = (
        "Quyidagi ma'lumotlarni diqqat bilan tekshiring:\n\n"
        f"👤 F.I.Sh: {esc(data['full_name'])}\n"
        f"💼 Lavozim: {esc(data['position'])}\n"
        f"🏢 Bo'lim: {esc(data['department'])}\n"
        f"📱 Telefon: {esc(data['phone'])}\n\n"
        "Hammasi to'g'rimi?"
    )
    await message.answer(summary, reply_markup=registration_confirm_kb())


@router.message(RegistrationStates.waiting_phone)
async def wrong_phone(message: Message):
    await message.answer('Iltimos, pastdagi "📱 Raqamni ulashish" tugmasidan foydalaning.')


@router.callback_query(RegistrationStates.confirming, F.data == "reg:restart")
async def restart_registration(callback: CallbackQuery, state: FSMContext):
    """Xodim xato kiritganini payqasa - hammasini qaytadan kiritish imkoniyati."""
    data = await state.get_data()
    next_action = data.get("next_action")
    await state.set_data({"next_action": next_action})
    await state.set_state(RegistrationStates.waiting_fullname)
    await callback.message.edit_text("🔄 Ma'lumotlarni qaytadan kiritamiz.")
    await callback.message.answer("F.I.Sh ni to'liq kiriting:", reply_markup=cancel_kb())
    await callback.answer()


@router.callback_query(RegistrationStates.confirming, F.data == "reg:cancel")
async def cancel_registration(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Bekor qilindi.")
    await callback.message.answer("Asosiy menyu:", reply_markup=main_menu_kb(callback.from_user.id))
    await callback.answer()


@router.callback_query(RegistrationStates.confirming, F.data == "reg:confirm")
async def confirm_registration(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    full_name = data["full_name"]
    position = data["position"]
    department = data["department"]
    phone = data["phone"]
    next_action = data.get("next_action")

    await create_user(
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        full_name=full_name,
        position=position,
        department=department,
        phone=phone,
    )

    await audit.log(
        {"id": None, "name": full_name, "role": None, "source": "bot", "ip": None},
        "user_registered", "user", callback.from_user.id, f"{position}, {department}",
    )
    await state.clear()
    await callback.message.edit_text("✅ Ma'lumotlaringiz saqlandi.")

    if next_action == "personal_appeal":
        await state.set_state(PersonalStates.waiting_appeal_text)
        await callback.message.answer(
            "Endi shaxsiy masalangiz yuzasidan murojaatingizni yozing:",
            reply_markup=cancel_kb(),
        )
    elif next_action == "proposal_appeal":
        await state.set_state(ProposalStates.waiting_appeal_text)
        await callback.message.answer(
            "Endi taklifingizni batafsil yozing:",
            reply_markup=cancel_kb(),
        )
    elif next_action == "reception_booking":
        await state.update_data(full_name=full_name, phone=phone)
        await state.set_state(ReceptionStates.choosing_date)
        await callback.message.answer("Qaysi kunga yozilmoqchisiz?", reply_markup=dates_kb())
    else:
        await callback.message.answer("Asosiy menyu:", reply_markup=main_menu_kb(callback.from_user.id))

    await callback.answer()
