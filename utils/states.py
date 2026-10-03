from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    """Umumiy ro'yxatdan o'tish / ma'lumotlarni tahrirlash oqimi.
    Shaxsiy masala, direktor qabuliga yozilish va 'Ma'lumotlarimni tahrirlash'
    tugmasi - barchasi shu bitta oqimdan foydalanadi."""
    waiting_fullname = State()
    waiting_position = State()
    waiting_department = State()
    waiting_phone = State()
    confirming = State()          # kiritilgan ma'lumotlarni tasdiqlash bosqichi


class PersonalStates(StatesGroup):
    """Shaxsiy masalalar bo'limi uchun holatlar."""
    waiting_appeal_text = State()


class ProposalStates(StatesGroup):
    """Takliflar bo'limi uchun holatlar."""
    waiting_appeal_text = State()


class CorruptionStates(StatesGroup):
    """Korrupsiyaga guvoh bo'lish bo'limi uchun holatlar."""
    waiting_text = State()


class ReceptionStates(StatesGroup):
    """Direktor qabuliga yozilish bo'limi uchun holatlar."""
    choosing_date = State()
    choosing_time = State()
    waiting_reason = State()


class AdminStates(StatesGroup):
    """Admin panel uchun holatlar (javob yozish, xabar tarqatish)."""
    waiting_comment = State()
    waiting_broadcast = State()
    waiting_new_admin_id = State()
    waiting_new_admin_name = State()
