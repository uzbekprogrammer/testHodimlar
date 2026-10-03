from datetime import datetime, timedelta

from config import (
    WORK_START_HOUR,
    WORK_END_HOUR,
    LUNCH_START_HOUR,
    LUNCH_END_HOUR,
    RECEPTION_DAYS_AHEAD,
)

UZ_WEEKDAYS = {
    0: "Dushanba",
    1: "Seshanba",
    2: "Chorshanba",
    3: "Payshanba",
    4: "Juma",
    5: "Shanba",
    6: "Yakshanba",
}


def get_next_working_days(count: int = RECEPTION_DAYS_AHEAD):
    """Ertangi kundan boshlab, faqat Dushanba-Juma kunlarini qaytaradi (1 ish haftalik)."""
    days = []
    current = datetime.now() + timedelta(days=1)
    while len(days) < count:
        if current.weekday() < 5:  # 0=Dushanba ... 4=Juma
            days.append(current.date())
        current += timedelta(days=1)
    return days


def format_date_label(d) -> str:
    return f"{d.strftime('%d.%m.%Y')} ({UZ_WEEKDAYS[d.weekday()]})"


def get_all_slots():
    """Ish kuni davomidagi soatlik slotlar, tushlik vaqti (12:00-13:00) chiqarib tashlanadi."""
    slots = []
    for hour in range(WORK_START_HOUR, WORK_END_HOUR):
        if LUNCH_START_HOUR <= hour < LUNCH_END_HOUR:
            continue
        slots.append(f"{hour:02d}:00")
    return slots
