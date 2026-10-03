"""Роли администраторов. Источник правды — таблица admins; здесь быстрый кэш в памяти
(обновляется при любом изменении админов), чтобы проверки в обработчиках не ходили в БД."""

ROLE_SUPERADMIN = "superadmin"
ROLE_DIRECTOR = "director"
ROLE_LAWYER = "lawyer"
ROLE_SECRETARY = "secretary"

ROLE_LABELS = {
    ROLE_SUPERADMIN: "Суперадминистратор",
    ROLE_DIRECTOR: "Руководитель",
    ROLE_LAWYER: "Юрист",
    ROLE_SECRETARY: "Секретарь",
}

_roles: dict[int, str] = {}


def set_cache(mapping: dict[int, str]) -> None:
    _roles.clear()
    _roles.update(mapping)


def role_of(user_id: int) -> str | None:
    return _roles.get(user_id)


def ids_with_role(*roles: str) -> list[int]:
    return [uid for uid, r in _roles.items() if r in roles]


def is_superadmin(user_id: int) -> bool:
    return _roles.get(user_id) == ROLE_SUPERADMIN


def is_director(user_id: int) -> bool:
    return _roles.get(user_id) == ROLE_DIRECTOR


def is_lawyer(user_id: int) -> bool:
    return _roles.get(user_id) == ROLE_LAWYER


def is_secretary(user_id: int) -> bool:
    return _roles.get(user_id) == ROLE_SECRETARY


def is_admin(user_id: int) -> bool:
    return user_id in _roles
