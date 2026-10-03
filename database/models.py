from database.db import execute, fetchall, fetchone, get_conn


# ---------------------- USERS ----------------------

async def get_user(telegram_id: int):
    return await fetchone("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))


async def create_user(telegram_id, username, full_name, position, department, phone):
    await execute(
        """
        INSERT INTO users (telegram_id, username, full_name, position, department, phone)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(telegram_id) DO UPDATE SET
            username=excluded.username,
            full_name=excluded.full_name,
            position=excluded.position,
            department=excluded.department,
            phone=excluded.phone
        """,
        (telegram_id, username, full_name, position, department, phone),
    )


async def get_all_users():
    rows = await fetchall("SELECT telegram_id FROM users")
    return [r["telegram_id"] for r in rows]


# ---------------------- APPEALS ----------------------

async def create_appeal(telegram_id, username, full_name, appeal_type, text, file_id=None, file_type=None):
    return await execute(
        """
        INSERT INTO appeals (telegram_id, username, full_name, appeal_type, text, file_id, file_type)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (telegram_id, username, full_name, appeal_type, text, file_id, file_type),
    )


async def get_appeal(appeal_id: int):
    return await fetchone("SELECT * FROM appeals WHERE id = ?", (appeal_id,))


async def answer_appeal(appeal_id: int, comment: str, answered_by: str, answered_by_id: int | None = None):
    await execute(
        """
        UPDATE appeals
        SET status='javob_berildi', admin_comment=?, answered_by=?, answered_by_id=?,
            answered_at=datetime('now'), updated_at=datetime('now')
        WHERE id=?
        """,
        (comment, answered_by, answered_by_id, appeal_id),
    )


async def set_appeal_status(appeal_id: int, status: str):
    await execute(
        "UPDATE appeals SET status=?, updated_at=datetime('now') WHERE id=?", (status, appeal_id)
    )


# ---------------------- APPOINTMENTS ----------------------

async def create_appointment(telegram_id, full_name, phone, reason, date, time):
    return await execute(
        """
        INSERT INTO appointments (telegram_id, full_name, phone, reason, appointment_date, appointment_time)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (telegram_id, full_name, phone, reason, date, time),
    )


async def get_appointment(appointment_id: int):
    return await fetchone("SELECT * FROM appointments WHERE id = ?", (appointment_id,))


async def get_booked_slots(date: str):
    """Занятые (не отклонённые) слоты на дату."""
    rows = await fetchall(
        "SELECT appointment_time FROM appointments WHERE appointment_date = ? AND status != 'rad_etildi'",
        (date,),
    )
    return [r["appointment_time"] for r in rows]


async def update_appointment_status(appointment_id: int, status: str, comment: str = None, decided_by: str = None):
    await execute(
        """
        UPDATE appointments
        SET status=?, director_comment=?, decided_by=?, decided_at=datetime('now')
        WHERE id=?
        """,
        (status, comment, decided_by, appointment_id),
    )


# ---------------------- ОЧИСТКА БАЗЫ (только superadmin) ----------------------

async def clear_all_data():
    """Удаляет пользователей, обращения и записи на приём. Админы и история действий сохраняются."""
    conn = await get_conn()
    await conn.execute("DELETE FROM users")
    await conn.execute("DELETE FROM appeals")
    await conn.execute("DELETE FROM appointments")
    await conn.execute(
        "DELETE FROM sqlite_sequence WHERE name IN ('users','appeals','appointments')"
    )
    await conn.commit()
