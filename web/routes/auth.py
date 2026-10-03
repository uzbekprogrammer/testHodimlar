import secrets

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from config import WEB_SECURE_COOKIES
from database.db import execute, fetchall
from services import admins as adm
from services import audit
from web import security
from web.app import render
from web.deps import actor, current_user, form_with_csrf

router = APIRouter()
_DUMMY_HASH = adm.hash_password("dummy-password-for-timing")


def _set_cookie(resp, name, value, max_age=None):
    resp.set_cookie(name, value, httponly=True, samesite="strict", secure=WEB_SECURE_COOKIES, path="/", max_age=max_age)


@router.get("/login")
async def login_page(request: Request):
    if request.state.user:
        return RedirectResponse("/", status_code=303)
    token = secrets.token_urlsafe(24)
    resp = render(request, "login.html", token=token, error=None, username="")
    _set_cookie(resp, security.LOGIN_CSRF_COOKIE, token, 1800)
    return resp


@router.post("/login")
async def login(request: Request):
    form = await request.form()
    username = str(form.get("username", "")).strip()[:64]
    password = str(form.get("password", ""))[:256]
    ip = security.client_ip(request)

    def fail(msg: str, code: int = 401):
        token = secrets.token_urlsafe(24)
        resp = render(request, "login.html", code, token=token, error=msg, username=username)
        _set_cookie(resp, security.LOGIN_CSRF_COOKIE, token, 1800)
        return resp

    # CSRF для формы входа: токен в cookie должен совпасть с токеном из формы
    if not security.safe_equal(str(form.get("token", "")), request.cookies.get(security.LOGIN_CSRF_COOKIE, "")):
        return fail("Сессия формы устарела. Повторите вход.", 400)
    if security.limiter.locked(ip, username):
        await audit.log({"id": None, "name": username or "—", "role": None, "source": "web", "ip": ip}, "login_failed", details="Блокировка: слишком много попыток")
        return fail("Слишком много неудачных попыток. Подождите 15 минут.", 429)

    admin = await adm.get_by_username(username) if username else None
    ok = adm.verify_password(password, admin["password_hash"] if admin else _DUMMY_HASH)
    if not (admin and ok and admin["is_active"]):
        security.limiter.fail(ip, username)
        await audit.log({"id": None, "name": username or "—", "role": None, "source": "web", "ip": ip}, "login_failed", details="Неверный логин или пароль")
        return fail("Неверный логин или пароль.")

    security.limiter.reset(ip, username)
    token, _ = await security.create_session(admin["id"], ip, request.headers.get("user-agent", ""))
    await audit.log(audit.actor_from_admin(admin, "web", ip), "login")
    resp = RedirectResponse("/profile" if admin["must_change_pw"] else "/", status_code=303)
    _set_cookie(resp, security.COOKIE, token)
    resp.delete_cookie(security.LOGIN_CSRF_COOKIE)
    return resp


@router.post("/logout")
async def logout(request: Request):
    form, user = await form_with_csrf(request)
    await security.destroy_session(request.cookies.get(security.COOKIE))
    await audit.log(actor(user, request), "logout")
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(security.COOKIE)
    return resp


@router.get("/profile")
async def profile(request: Request):
    user = current_user(request)
    sessions = await fetchall(
        "SELECT id, created_at, last_seen, ip, user_agent FROM web_sessions WHERE admin_id=? ORDER BY last_seen DESC",
        (user["id"],),
    )
    return render(request, "profile.html", sessions=sessions, current_sid=request.state.session_id)


@router.post("/profile/password")
async def change_password(request: Request):
    form, user = await form_with_csrf(request)
    current, new, repeat = (str(form.get(k, "")) for k in ("current", "new", "repeat"))
    full = await adm.get_by_id(user["id"])
    if not adm.verify_password(current, full["password_hash"]):
        return RedirectResponse("/profile?err=wrong_pw", status_code=303)
    if new != repeat or adm.password_problem(new) or new == current:
        return RedirectResponse("/profile?err=weak_pw", status_code=303)
    await adm.set_password(user["id"], new)         # завершает все сессии, включая текущую
    await audit.log(actor(user, request), "password_changed")
    token, _ = await security.create_session(user["id"], security.client_ip(request), request.headers.get("user-agent", ""))
    resp = RedirectResponse("/profile?ok=pw_changed", status_code=303)
    _set_cookie(resp, security.COOKIE, token)
    return resp


@router.post("/profile/sessions/close-others")
async def close_other_sessions(request: Request):
    form, user = await form_with_csrf(request)
    await execute("DELETE FROM web_sessions WHERE admin_id=? AND id != ?", (user["id"], request.state.session_id))
    return RedirectResponse("/profile?ok=sessions_closed", status_code=303)
