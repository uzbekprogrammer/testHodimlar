from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from database.db import fetchall
from services import audit, stats
from utils.roles import ROLE_DIRECTOR, ROLE_SUPERADMIN, ROLE_SECRETARY
from web.app import render
from web.charts import bars, donut
from web.deps import require

router = APIRouter()


@router.get("/")
async def dashboard(request: Request, user=Depends(require())):
    o = await stats.overview()
    daily = await stats.daily(14)
    series = [{"label": d["d"][8:10] + "." + d["d"][5:7], "n": d["n"]} for d in daily]
    types = donut([
        {"label": "Коррупция", "n": o["corruption"], "cls": "c-red"},
        {"label": "Личные вопросы", "n": o["personal"], "cls": "c-blue"},
        {"label": "Предложения", "n": o["proposal"], "cls": "c-green"},
    ])
    role = user["role"]
    recent, pending_appts, activity = [], [], []
    if role != ROLE_SECRETARY:
        recent = await fetchall(
            "SELECT id, appeal_type, status, full_name, created_at FROM appeals ORDER BY id DESC LIMIT 7"
        )
        pending_appts = await fetchall(
            "SELECT * FROM appointments WHERE status='kutilmoqda' ORDER BY appointment_date, appointment_time LIMIT 5"
        )
    else:
        pending_appts = await fetchall(
            "SELECT * FROM appointments WHERE status='tasdiqlandi' AND appointment_date >= date('now','+5 hours') "
            "ORDER BY appointment_date, appointment_time LIMIT 8"
        )
    if role in (ROLE_SUPERADMIN, ROLE_DIRECTOR):
        activity, _ = await audit.search(limit=8)
    return render(request, "dashboard.html", o=o, chart=bars(series), types=types,
                  recent=recent, appts=pending_appts, activity=activity, ACTIONS=audit.ACTION_LABELS)


@router.get("/api/stats")
async def api_stats(user=Depends(require())):
    o = await stats.overview()
    return JSONResponse(o, headers={"Cache-Control": "no-store"})
