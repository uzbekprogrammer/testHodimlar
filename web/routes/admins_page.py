import re

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from services import admins as adm
from services import audit
from utils.roles import ROLE_LABELS, ROLE_SUPERADMIN
from web.app import Forbidden, render
from web.deps import actor, form_with_csrf, require

router = APIRouter()
LOGIN_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")


def _tg(value: str):
    value = value.strip()
    return int(value) if value.isdigit() and 0 < int(value) < 10 ** 15 else None


@router.get("/admins")
async def admins(request: Request, user=Depends(require(ROLE_SUPERADMIN))):
    return render(request, "admins.html", items=await adm.list_admins(), roles=ROLE_LABELS, created=None)


async def _super(request: Request):
    form, user = await form_with_csrf(request)
    if user["role"] != ROLE_SUPERADMIN:
        raise Forbidden()
    return form, user


@router.post("/admins/add")
async def add(request: Request):
    form, user = await _super(request)
    name = str(form.get("full_name", "")).strip()
    role = str(form.get("role", ""))
    username = str(form.get("username", "")).strip() or None
    tg = _tg(str(form.get("telegram_id", ""))) if str(form.get("telegram_id", "")).strip() else None
    if not 2 <= len(name) <= 80 or role not in adm.VALID_ROLES or (username and not LOGIN_RE.match(username)) \
            or (str(form.get("telegram_id", "")).strip() and tg is None) or not (username or tg):
        return RedirectResponse("/admins?err=bad_input", status_code=303)
    if (username and await adm.get_by_username(username)) or (tg and await _tg_taken(tg)):
        return RedirectResponse("/admins?err=taken", status_code=303)
    password = adm.generate_password() if username else None
    new_id = await adm.create_admin(name, role, tg, username, password)
    await audit.log(actor(user, request), "admin_added", "admin", new_id, f"{name} ({role})")
    created = {"name": name, "username": username, "password": password}
    return render(request, "admins.html", items=await adm.list_admins(), roles=ROLE_LABELS, created=created)


async def _tg_taken(tg: int) -> bool:
    from database.db import scalar
    return bool(await scalar("SELECT 1 FROM admins WHERE telegram_id=?", (tg,)))


@router.post("/admins/{admin_id}/update")
async def update(admin_id: int, request: Request):
    form, user = await _super(request)
    target = await adm.get_by_id(admin_id)
    if not target:
        return RedirectResponse("/admins?err=not_found", status_code=303)
    role = str(form.get("role", target["role"]))
    active = 1 if form.get("is_active") else 0
    name = str(form.get("full_name", target["full_name"])).strip()
    if role not in adm.VALID_ROLES or not 2 <= len(name) <= 80:
        return RedirectResponse("/admins?err=bad_input", status_code=303)
    tg_raw = str(form.get("telegram_id", "")).strip()
    tg = _tg(tg_raw) if tg_raw else None
    if tg_raw and tg is None:
        return RedirectResponse("/admins?err=bad_input", status_code=303)
    if tg and tg != target["telegram_id"] and await _tg_taken(tg):
        return RedirectResponse("/admins?err=taken", status_code=303)
    demoting = target["role"] == ROLE_SUPERADMIN and (role != ROLE_SUPERADMIN or not active)
    if demoting and await adm.active_superadmin_count(admin_id) == 0:
        return RedirectResponse("/admins?err=last_super", status_code=303)
    if target["id"] == user["id"] and not active:
        return RedirectResponse("/admins?err=self", status_code=303)
    await adm.update_admin(admin_id, full_name=name, role=role, telegram_id=tg, is_active=active)
    await audit.log(actor(user, request), "admin_updated", "admin", admin_id, f"{name}: {target['role']}→{role}, активен={active}")
    return RedirectResponse("/admins?ok=admin_updated", status_code=303)


@router.post("/admins/{admin_id}/reset-password")
async def reset_password(admin_id: int, request: Request):
    form, user = await _super(request)
    target = await adm.get_by_id(admin_id)
    if not target:
        return RedirectResponse("/admins?err=not_found", status_code=303)
    username = target["username"] or f"user{target['id']}"
    if not target["username"]:
        await adm.update_admin(admin_id, username=username)
    password = adm.generate_password()
    await adm.set_password(admin_id, password, must_change=True)
    await audit.log(actor(user, request), "admin_password_reset", "admin", admin_id, f"Логин: {username}")
    return render(request, "admins.html", items=await adm.list_admins(), roles=ROLE_LABELS,
                  created={"name": target["full_name"], "username": username, "password": password})


@router.post("/admins/{admin_id}/delete")
async def delete(admin_id: int, request: Request):
    form, user = await _super(request)
    target = await adm.get_by_id(admin_id)
    if not target:
        return RedirectResponse("/admins?err=not_found", status_code=303)
    if target["id"] == user["id"]:
        return RedirectResponse("/admins?err=self", status_code=303)
    if target["role"] == ROLE_SUPERADMIN and await adm.active_superadmin_count(admin_id) == 0:
        return RedirectResponse("/admins?err=last_super", status_code=303)
    await adm.delete_admin(admin_id)
    await audit.log(actor(user, request), "admin_removed", "admin", admin_id, target["full_name"])
    return RedirectResponse("/admins?ok=admin_deleted", status_code=303)
