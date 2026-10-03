from datetime import date as date_cls

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from database.db import fetchall
from services.core import decide_appointment
from utils.roles import ROLE_DIRECTOR, ROLE_SECRETARY
from web.app import Forbidden, render
from web.deps import actor, form_with_csrf, require

router = APIRouter()
STATUSES = {"kutilmoqda": "Ожидает", "tasdiqlandi": "Подтверждён", "rad_etildi": "Отклонён"}
WEEKDAYS = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]


@router.get("/appointments")
async def appointments(request: Request, user=Depends(require())):
    status = request.query_params.get("status", "kutilmoqda")
    if user["role"] == ROLE_SECRETARY:
        status = "tasdiqlandi"            # секретарь видит только подтверждённые приёмы
    where, args = "", ()
    if status in STATUSES:
        where, args = "WHERE status=?", (status,)
    else:
        status = "all"
    rows = await fetchall(
        f"SELECT * FROM appointments {where} ORDER BY appointment_date DESC, appointment_time DESC LIMIT 300", args
    )
    counts = {r["status"]: r["n"] for r in await fetchall("SELECT status, COUNT(*) AS n FROM appointments GROUP BY status")}
    groups: dict[str, list] = {}
    for r in rows:
        groups.setdefault(r["appointment_date"], []).append(r)
    days = []
    for d in sorted(groups, reverse=(status != "kutilmoqda" and status != "tasdiqlandi")):
        dt = date_cls.fromisoformat(d)
        days.append({"date": dt.strftime("%d.%m.%Y"), "weekday": WEEKDAYS[dt.weekday()], "items": sorted(groups[d], key=lambda x: x["appointment_time"])})
    return render(request, "appointments.html", days=days, status=status, STATUSES=STATUSES, counts=counts,
                  can_decide=user["role"] == ROLE_DIRECTOR, total=len(rows))


@router.post("/appointments/{appt_id}/{decision}")
async def decide(appt_id: int, decision: str, request: Request):
    form, user = await form_with_csrf(request)
    if decision not in ("confirm", "reject"):
        raise Forbidden()
    ok, msg = await decide_appointment(request.app.state.bot, appt_id, decision == "confirm", actor(user, request))
    if not ok:
        return RedirectResponse(f"/appointments?err={'denied' if 'только' in msg else 'state'}", status_code=303)
    return RedirectResponse(f"/appointments?ok={'appt_confirmed' if decision == 'confirm' else 'appt_rejected'}", status_code=303)
