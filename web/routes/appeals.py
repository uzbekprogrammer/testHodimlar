import csv
import io
import mimetypes

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response, StreamingResponse

from database import models
from database.db import fetchall, scalar
from services import audit
from services.core import answer_appeal
from utils.roles import ROLE_DIRECTOR, ROLE_LAWYER, ROLE_SUPERADMIN
from utils.timefmt import fmt_dt
from web.app import Forbidden, render
from web.deps import actor, form_with_csrf, require

router = APIRouter()
PER_PAGE = 20
TYPES = {"corruption": "Коррупция", "personal": "Личный вопрос", "taklif": "Предложение"}
STATUSES = {"yangi": "Новое", "v_rabote": "В работе", "javob_berildi": "Отвечено"}
SORTS = {"new": "a.id DESC", "old": "a.id ASC", "status": "a.status ASC, a.id DESC"}   # белый список сортировок


def _can_see(user: dict) -> bool:
    from config import SUPERADMIN_SEE_APPEAL_TEXT
    return user["role"] != ROLE_SUPERADMIN or SUPERADMIN_SEE_APPEAL_TEXT


def _filters(params, see_text: bool):
    where, args = [], []
    t, s = params.get("type", ""), params.get("status", "")
    q = (params.get("q", "") or "").strip()[:100]
    d1, d2 = params.get("from", ""), params.get("to", "")
    if t in TYPES:
        where.append("a.appeal_type=?"); args.append(t)
    if s in STATUSES:
        where.append("a.status=?"); args.append(s)
    if q:
        like = f"%{q}%"
        if q.lstrip("#").isdigit():
            where.append("a.id=?"); args.append(int(q.lstrip("#")))
        elif see_text:
            where.append("(a.text LIKE ? OR (a.appeal_type!='corruption' AND a.full_name LIKE ?))"); args += [like, like]
        else:
            where.append("(a.appeal_type!='corruption' AND a.full_name LIKE ?)"); args.append(like)
    if d1:
        where.append("date(a.created_at,'+5 hours') >= ?"); args.append(d1[:10])
    if d2:
        where.append("date(a.created_at,'+5 hours') <= ?"); args.append(d2[:10])
    return (" WHERE " + " AND ".join(where)) if where else "", tuple(args), {"type": t, "status": s, "q": q, "from": d1, "to": d2}


def _page(params) -> int:
    try:
        return max(1, int(params.get("page", "1")))
    except ValueError:
        return 1


@router.get("/appeals")
async def list_appeals(request: Request, user=Depends(require(ROLE_SUPERADMIN, ROLE_DIRECTOR, ROLE_LAWYER))):
    p = request.query_params
    where, args, flt = _filters(p, _can_see(user))
    sort = p.get("sort", "new")
    order = SORTS.get(sort, SORTS["new"])
    page = _page(p)
    total = await scalar(f"SELECT COUNT(*) FROM appeals a{where}", args)
    rows = await fetchall(
        f"""SELECT a.id, a.appeal_type, a.status, a.full_name, a.created_at, a.answered_at, a.file_type,
                   SUBSTR(a.text,1,140) AS preview
            FROM appeals a{where} ORDER BY {order} LIMIT ? OFFSET ?""",
        args + (PER_PAGE, (page - 1) * PER_PAGE),
    )
    counts = {r["status"]: r["n"] for r in await fetchall("SELECT status, COUNT(*) AS n FROM appeals GROUP BY status")}
    qs = "&".join(f"{k}={v}" for k, v in {**flt, "sort": sort}.items() if v)
    return render(request, "appeals.html", rows=rows, total=total, page=page, pages=max(1, -(-total // PER_PAGE)),
                  flt=flt, sort=sort, TYPES=TYPES, STATUSES=STATUSES, counts=counts, qs=qs)


@router.get("/appeals/export.csv")
async def export_csv(request: Request, user=Depends(require(ROLE_SUPERADMIN, ROLE_DIRECTOR, ROLE_LAWYER))):
    see = _can_see(user)
    where, args, _ = _filters(request.query_params, see)
    rows = await fetchall(
        f"SELECT a.* FROM appeals a{where} ORDER BY a.id DESC LIMIT 5000", args
    )

    def safe(v):
        v = "" if v is None else str(v)
        return "'" + v if v[:1] in ("=", "+", "-", "@", "\t", "\r") else v   # защита от CSV-инъекций

    buf = io.StringIO()
    buf.write("﻿")
    w = csv.writer(buf, delimiter=";")
    w.writerow(["№", "Тип", "Статус", "Автор", "Создано", "Отвечено", "Ответил", "Текст", "Ответ"])
    for r in rows:
        w.writerow([
            r["id"], TYPES.get(r["appeal_type"], r["appeal_type"]), STATUSES.get(r["status"], r["status"]),
            safe(r["full_name"]) if r["appeal_type"] != "corruption" else "анонимно",
            fmt_dt(r["created_at"]), fmt_dt(r["answered_at"]), safe(r["answered_by"]),
            safe(r["text"]) if see else "", safe(r["admin_comment"]) if see else "",
        ])
    await audit.log(actor(user, request), "export", "appeals", None, f"CSV, строк: {len(rows)}")
    return Response(buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="appeals.csv"'})


@router.get("/appeals/{appeal_id}")
async def appeal_detail(appeal_id: int, request: Request,
                        user=Depends(require(ROLE_SUPERADMIN, ROLE_DIRECTOR, ROLE_LAWYER))):
    a = await models.get_appeal(appeal_id)
    if not a:
        return RedirectResponse("/appeals?err=not_found", status_code=303)
    history = await audit_for(appeal_id)
    return render(request, "appeal_detail.html", a=a, TYPES=TYPES, STATUSES=STATUSES, history=history,
                  can_reply=user["role"] in (ROLE_DIRECTOR, ROLE_LAWYER), ACTIONS=audit.ACTION_LABELS)


async def audit_for(appeal_id: int):
    return await fetchall(
        "SELECT * FROM audit_log WHERE entity='appeal' AND entity_id=? ORDER BY id DESC LIMIT 20", (str(appeal_id),)
    )


@router.post("/appeals/{appeal_id}/reply")
async def reply(appeal_id: int, request: Request):
    form, user = await form_with_csrf(request)
    ok, msg = await answer_appeal(request.app.state.bot, appeal_id, str(form.get("text", "")), actor(user, request))
    if not ok:
        if "права" in msg:
            raise Forbidden()
        return RedirectResponse(f"/appeals/{appeal_id}?err=bad_input", status_code=303)
    return RedirectResponse(f"/appeals/{appeal_id}?ok={'reply_sent' if 'Ответ отправлен' in msg else 'reply_saved'}", status_code=303)


@router.post("/appeals/{appeal_id}/status")
async def change_status(appeal_id: int, request: Request):
    form, user = await form_with_csrf(request)
    if user["role"] not in (ROLE_SUPERADMIN, ROLE_DIRECTOR, ROLE_LAWYER):
        raise Forbidden()
    status = str(form.get("status", ""))
    appeal = await models.get_appeal(appeal_id)
    if not appeal or status not in ("yangi", "v_rabote"):
        return RedirectResponse(f"/appeals/{appeal_id}?err=bad_input", status_code=303)
    if appeal["status"] == "javob_berildi":
        return RedirectResponse(f"/appeals/{appeal_id}?err=state", status_code=303)
    await models.set_appeal_status(appeal_id, status)
    await audit.log(actor(user, request), "appeal_status", "appeal", appeal_id, STATUSES[status])
    return RedirectResponse(f"/appeals/{appeal_id}?ok=status_ok", status_code=303)


@router.get("/appeals/{appeal_id}/file")
async def appeal_file(appeal_id: int, request: Request,
                      user=Depends(require(ROLE_SUPERADMIN, ROLE_DIRECTOR, ROLE_LAWYER))):
    """Вложение скачивается через бота (Telegram file API); отдаётся безопасно: документы — только как attachment."""
    a = await models.get_appeal(appeal_id)
    if not a or not a["file_id"] or not _can_see(user):
        raise Forbidden()
    bot = request.app.state.bot
    try:
        info = await bot.get_file(a["file_id"])
        if info.file_size and info.file_size > 20 * 1024 * 1024:
            raise Forbidden()
        buf = io.BytesIO()
        await bot.download_file(info.file_path, destination=buf)
    except Forbidden:
        raise
    except Exception:
        return Response("Файл недоступен в Telegram.", status_code=404)
    buf.seek(0)
    name = (info.file_path or "file").rsplit("/", 1)[-1]
    ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
    headers = {"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=300"}
    if a["file_type"] == "photo" and ctype in ("image/jpeg", "image/png", "image/webp"):
        headers["Content-Disposition"] = f'inline; filename="appeal-{appeal_id}.jpg"'
    else:
        ctype = "application/octet-stream"
        safe = "".join(c for c in name if c.isalnum() or c in "._-") or "file"
        headers["Content-Disposition"] = f'attachment; filename="{safe}"'
    return StreamingResponse(buf, media_type=ctype, headers=headers)
