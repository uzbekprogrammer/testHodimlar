from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from database.db import fetchall, fetchone, scalar
from utils.roles import ROLE_DIRECTOR, ROLE_LAWYER, ROLE_SUPERADMIN
from web.app import render
from web.deps import require

router = APIRouter()
PER_PAGE = 25
ALLOWED = (ROLE_SUPERADMIN, ROLE_DIRECTOR, ROLE_LAWYER)


@router.get("/users")
async def users(request: Request, user=Depends(require(*ALLOWED))):
    p = request.query_params
    q = (p.get("q", "") or "").strip()[:80]
    dep = (p.get("dep", "") or "").strip()[:80]
    try:
        page = max(1, int(p.get("page", "1")))
    except ValueError:
        page = 1
    where, args = [], []
    if q:
        like = f"%{q}%"
        where.append("(u.full_name LIKE ? OR u.phone LIKE ? OR u.position LIKE ? OR u.username LIKE ?)")
        args += [like] * 4
    if dep:
        where.append("u.department=?"); args.append(dep)
    w = (" WHERE " + " AND ".join(where)) if where else ""
    total = await scalar(f"SELECT COUNT(*) FROM users u{w}", tuple(args))
    # корруп. обращения намеренно НЕ учитываются — они анонимны для сотрудников-админов
    rows = await fetchall(
        f"""SELECT u.*, (SELECT COUNT(*) FROM appeals a WHERE a.telegram_id=u.telegram_id AND a.appeal_type!='corruption') AS appeals_n,
                   (SELECT COUNT(*) FROM appointments p WHERE p.telegram_id=u.telegram_id) AS appts_n
            FROM users u{w} ORDER BY u.id DESC LIMIT ? OFFSET ?""",
        tuple(args) + (PER_PAGE, (page - 1) * PER_PAGE),
    )
    deps = await fetchall("SELECT DISTINCT department FROM users WHERE department IS NOT NULL AND department != '' ORDER BY department")
    return render(request, "users.html", rows=rows, total=total, page=page, pages=max(1, -(-total // PER_PAGE)),
                  q=q, dep=dep, deps=[d["department"] for d in deps])


@router.get("/users/{tg_id}")
async def user_detail(tg_id: int, request: Request, user=Depends(require(*ALLOWED))):
    u = await fetchone("SELECT * FROM users WHERE telegram_id=?", (tg_id,))
    if not u:
        return RedirectResponse("/users?err=not_found", status_code=303)
    appeals = await fetchall(
        "SELECT id, appeal_type, status, created_at, SUBSTR(text,1,100) AS preview FROM appeals "
        "WHERE telegram_id=? AND appeal_type!='corruption' ORDER BY id DESC LIMIT 50", (tg_id,)
    )
    appts = await fetchall("SELECT * FROM appointments WHERE telegram_id=? ORDER BY id DESC LIMIT 50", (tg_id,))
    return render(request, "user_detail.html", u=u, appeals=appeals, appts=appts)
