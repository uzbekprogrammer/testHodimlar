import csv
import io

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from services import audit
from utils.roles import ROLE_DIRECTOR, ROLE_SUPERADMIN
from utils.timefmt import fmt_dt
from web.app import render
from web.deps import actor, require

router = APIRouter()
PER_PAGE = 40


def _params(p):
    return {
        "source": p.get("source", "") if p.get("source") in ("bot", "web", "system") else "",
        "action": p.get("action", "") if p.get("action") in audit.ACTION_LABELS else "",
        "q": (p.get("q", "") or "").strip()[:80],
        "date_from": p.get("from", "")[:10], "date_to": p.get("to", "")[:10],
    }


@router.get("/audit")
async def audit_list(request: Request, user=Depends(require(ROLE_SUPERADMIN, ROLE_DIRECTOR))):
    p = request.query_params
    flt = _params(p)
    try:
        page = max(1, int(p.get("page", "1")))
    except ValueError:
        page = 1
    rows, total = await audit.search(limit=PER_PAGE, offset=(page - 1) * PER_PAGE, **flt)
    qs = "&".join(f"{k}={v}" for k, v in {"source": flt["source"], "action": flt["action"], "q": flt["q"],
                                          "from": flt["date_from"], "to": flt["date_to"]}.items() if v)
    return render(request, "audit.html", rows=rows, total=total, page=page, pages=max(1, -(-total // PER_PAGE)),
                  flt=flt, ACTIONS=audit.ACTION_LABELS, qs=qs)


@router.get("/audit/export.csv")
async def audit_export(request: Request, user=Depends(require(ROLE_SUPERADMIN))):
    rows, _ = await audit.search(limit=10000, **_params(request.query_params))

    def safe(v):
        v = "" if v is None else str(v)
        return "'" + v if v[:1] in ("=", "+", "-", "@", "\t", "\r") else v

    buf = io.StringIO()
    buf.write("﻿")
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Время", "Источник", "Кто", "Роль", "Действие", "Объект", "ID", "Детали", "IP"])
    for r in rows:
        w.writerow([fmt_dt(r["ts"]), r["source"], safe(r["actor_name"]), r["actor_role"] or "",
                    audit.ACTION_LABELS.get(r["action"], r["action"]), r["entity"] or "", r["entity_id"] or "",
                    safe(r["details"]), r["ip"] or ""])
    await audit.log(actor(user, request), "export", "audit", None, f"CSV, строк: {len(rows)}")
    return Response(buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="audit.csv"'})
