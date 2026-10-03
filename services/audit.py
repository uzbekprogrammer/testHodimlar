from database.db import execute, fetchall, scalar


def actor_from_admin(admin: dict | None, source: str, ip: str | None = None) -> dict:
    if not admin:
        return {"id": None, "name": "system", "role": None, "source": source, "ip": ip}
    return {
        "id": admin.get("id"),
        "name": admin.get("full_name") or admin.get("username") or str(admin.get("telegram_id")),
        "role": admin.get("role"),
        "source": source,
        "ip": ip,
    }


async def log(actor: dict | None, action: str, entity: str | None = None, entity_id=None, details: str | None = None):
    actor = actor or {"id": None, "name": "system", "role": None, "source": "system", "ip": None}
    await execute(
        """INSERT INTO audit_log (source, actor_id, actor_name, actor_role, action, entity, entity_id, details, ip)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            actor.get("source", "system"), actor.get("id"), actor.get("name"), actor.get("role"),
            action, entity, None if entity_id is None else str(entity_id),
            (details or "")[:1000] or None, actor.get("ip"),
        ),
    )


ACTION_LABELS = {
    "login": "Вход на сайт",
    "login_failed": "Неудачный вход",
    "logout": "Выход",
    "password_changed": "Смена пароля",
    "appeal_created": "Новое обращение",
    "appeal_answered": "Ответ на обращение",
    "appeal_status": "Смена статуса обращения",
    "appointment_created": "Запись на приём",
    "appointment_confirmed": "Приём подтверждён",
    "appointment_rejected": "Приём отклонён",
    "broadcast": "Рассылка",
    "admin_added": "Добавлен администратор",
    "admin_updated": "Изменён администратор",
    "admin_removed": "Удалён администратор",
    "admin_password_reset": "Сброс пароля администратора",
    "cleardb": "Очистка базы",
    "export": "Экспорт данных",
    "user_registered": "Регистрация сотрудника",
    "system_start": "Запуск системы",
}


def _filters(source=None, action=None, q=None, date_from=None, date_to=None):
    where, params = [], []
    if source:
        where.append("source = ?"); params.append(source)
    if action:
        where.append("action = ?"); params.append(action)
    if q:
        like = f"%{q}%"
        where.append("(actor_name LIKE ? OR details LIKE ? OR entity_id LIKE ?)")
        params += [like, like, like]
    if date_from:
        where.append("date(ts,'+5 hours') >= ?"); params.append(date_from)
    if date_to:
        where.append("date(ts,'+5 hours') <= ?"); params.append(date_to)
    return (" WHERE " + " AND ".join(where)) if where else "", tuple(params)


async def search(limit=50, offset=0, **filters) -> tuple[list[dict], int]:
    w, p = _filters(**filters)
    total = await scalar(f"SELECT COUNT(*) FROM audit_log{w}", p)
    rows = await fetchall(
        f"SELECT * FROM audit_log{w} ORDER BY id DESC LIMIT ? OFFSET ?", p + (limit, offset)
    )
    return rows, total or 0
