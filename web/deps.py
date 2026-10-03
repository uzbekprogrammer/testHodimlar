from fastapi import Request

from web.app import ForcePasswordChange, Forbidden, NotAuthenticated
from web.security import safe_equal
from utils.roles import ROLE_SUPERADMIN


def current_user(request: Request) -> dict:
    user = request.state.user
    if not user:
        raise NotAuthenticated()
    # Принудительная смена временного пароля
    if user["must_change_pw"] and request.url.path not in ("/profile", "/profile/password", "/logout"):
        raise ForcePasswordChange()
    return user


def require(*roles: str):
    """Зависимость FastAPI: пускает только перечисленные роли (без аргументов — любого вошедшего)."""
    def dep(request: Request) -> dict:
        user = current_user(request)
        if roles and user["role"] not in roles:
            raise Forbidden()
        return user
    return dep


async def form_with_csrf(request: Request):
    """Читает форму и проверяет CSRF-токен. Возвращает (form, user)."""
    user = current_user(request)
    form = await request.form()
    if not safe_equal(str(form.get("csrf", "")), request.state.csrf):
        raise Forbidden()
    return form, user


def actor(user: dict, request: Request) -> dict:
    from web.security import client_ip
    return {"id": user["id"], "name": user["full_name"], "role": user["role"], "source": "web", "ip": client_ip(request)}


def superadmin_only(request: Request) -> dict:
    return require(ROLE_SUPERADMIN)(request)
