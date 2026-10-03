import asyncio
import json
import logging
import secrets
import time
from pathlib import Path

from aiogram import Bot
from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import BOT_NAME_RU, PLATFORM_NAME, SUPERADMIN_SEE_APPEAL_TEXT, WEB_SECURE_COOKIES
from utils.roles import ROLE_DIRECTOR, ROLE_LABELS, ROLE_LAWYER, ROLE_SECRETARY, ROLE_SUPERADMIN
from utils.timefmt import fmt_ago, fmt_dt
from web import security

log = logging.getLogger(__name__)
BASE = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE / "templates"))
templates.env.filters["dt"] = fmt_dt
templates.env.filters["ago"] = fmt_ago
templates.env.globals.update(ROLE_LABELS=ROLE_LABELS, BOT_NAME=BOT_NAME_RU, PLATFORM=PLATFORM_NAME)

# Нав-меню: (endpoint, подпись, иконка, роли)
NAV = [
    ("/", "Обзор", "home", None),
    ("/appeals", "Обращения", "inbox", (ROLE_SUPERADMIN, ROLE_DIRECTOR, ROLE_LAWYER)),
    ("/appointments", "Приём руководителя", "calendar", None),
    ("/users", "Сотрудники", "users", (ROLE_SUPERADMIN, ROLE_DIRECTOR, ROLE_LAWYER)),
    ("/monitoring", "Мониторинг", "pulse", (ROLE_SUPERADMIN, ROLE_DIRECTOR)),
    ("/audit", "История действий", "history", (ROLE_SUPERADMIN, ROLE_DIRECTOR)),
    ("/broadcast", "Рассылка", "send", None),
    ("/admins", "Администраторы", "shield", (ROLE_SUPERADMIN,)),
]

FLASH = {
    "reply_sent": "Ответ отправлен сотруднику.",
    "reply_saved": "Ответ сохранён, но сотрудник не получил сообщение в Telegram.",
    "status_ok": "Статус обращения обновлён.",
    "appt_confirmed": "Приём подтверждён, сотрудник и секретарь уведомлены.",
    "appt_rejected": "Приём отклонён, сотрудник уведомлен.",
    "admin_added": "Администратор добавлен.",
    "admin_updated": "Данные администратора сохранены.",
    "admin_deleted": "Администратор удалён.",
    "pw_changed": "Пароль изменён.",
    "sessions_closed": "Остальные сессии завершены.",
    "broadcast_ok": "Рассылка выполнена.",
    "denied": "Недостаточно прав для этого действия.",
    "bad_input": "Проверьте введённые данные.",
    "not_found": "Запись не найдена.",
    "state": "Действие уже выполнено или недоступно.",
    "last_super": "Нельзя отключить, понизить или удалить последнего суперадминистратора.",
    "self": "Нельзя выполнить это действие над собственной учётной записью.",
    "taken": "Такой логин или Telegram ID уже используется.",
    "weak_pw": "Пароль слишком простой: минимум 8 символов, буквы и цифры.",
    "wrong_pw": "Текущий пароль указан неверно.",
}


class NotAuthenticated(Exception):
    pass


class Forbidden(Exception):
    pass


class ForcePasswordChange(Exception):
    pass


def can(role: str, roles: tuple | None) -> bool:
    return roles is None or role in roles


def render(request: Request, name: str, status_code: int = 200, **ctx):
    user = getattr(request.state, "user", None)
    nonce_ctx = {
        "request": request,
        "user": user,
        "csrf": getattr(request.state, "csrf", ""),
        "nav": [n for n in NAV if user and can(user["role"], n[3])],
        "path": request.url.path,
        "flash_ok": FLASH.get(request.query_params.get("ok", "")),
        "flash_err": FLASH.get(request.query_params.get("err", "")),
        "see_text": user is not None and (user["role"] != ROLE_SUPERADMIN or SUPERADMIN_SEE_APPEAL_TEXT),
        "now": time.time(),
    }
    nonce_ctx.update(ctx)
    resp = templates.TemplateResponse(request, name, nonce_ctx, status_code=status_code)
    resp.headers["Cache-Control"] = "no-store"
    return resp


def create_app(bot: Bot) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.bot = bot
    app.add_middleware(GZipMiddleware, minimum_size=800)

    class _Static(StaticFiles):
        async def get_response(self, path, scope):
            resp = await super().get_response(path, scope)
            resp.headers["Cache-Control"] = "public, max-age=86400"
            return resp

    app.mount("/static", _Static(directory=str(BASE / "static")), name="static")

    @app.middleware("http")
    async def auth_and_headers(request: Request, call_next):
        request.state.user = None
        request.state.csrf = ""
        if not request.url.path.startswith("/static"):
            sess = await security.load_session(request.cookies.get(security.COOKIE))
            if sess:
                request.state.user = sess["admin"]
                request.state.csrf = sess["csrf"]
                request.state.session_id = sess["session_id"]
        try:
            response = await call_next(request)
        except NotAuthenticated:
            response = RedirectResponse("/login", status_code=303)
        response.headers.update({
            "Content-Security-Policy": (
                "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
                "object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
            ),
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "same-origin",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
            "Cross-Origin-Opener-Policy": "same-origin",
        })
        if WEB_SECURE_COOKIES:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    @app.exception_handler(NotAuthenticated)
    async def _na(request: Request, exc):
        if request.url.path.startswith("/api/"):
            return JSONResponse({"error": "auth"}, status_code=401)
        return RedirectResponse("/login", status_code=303)

    @app.exception_handler(ForcePasswordChange)
    async def _fpc(request: Request, exc):
        return RedirectResponse("/profile", status_code=303)

    @app.exception_handler(Forbidden)
    async def _forbidden(request: Request, exc):
        return render(request, "error.html", 403, code=403, title="Доступ запрещён",
                      text="У вашей роли нет доступа к этому разделу.")

    @app.exception_handler(404)
    async def _nf(request: Request, exc):
        return render(request, "error.html", 404, code=404, title="Страница не найдена",
                      text="Такой страницы не существует или она была удалена.")

    @app.exception_handler(Exception)
    async def _err(request: Request, exc):
        log.exception("Web error: %s", exc)
        return render(request, "error.html", 500, code=500, title="Внутренняя ошибка",
                      text="Что-то пошло не так. Попробуйте ещё раз; если ошибка повторяется — обратитесь к администратору.")

    from web.routes import auth, appeals, appointments, users, admins_page, audit_page, monitoring, broadcast, dashboard
    for module in (auth, dashboard, appeals, appointments, users, admins_page, audit_page, monitoring, broadcast):
        app.include_router(module.router)

    @app.on_event("startup")
    async def _startup():
        async def janitor():
            while True:
                try:
                    await security.purge_expired()
                except Exception:
                    log.exception("session purge failed")
                await asyncio.sleep(3600)
        app.state.janitor = asyncio.create_task(janitor())

    return app
