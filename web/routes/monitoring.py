import time

from fastapi import APIRouter, Depends, Request

from database.db import fetchall
from services import stats
from utils.roles import ROLE_DIRECTOR, ROLE_SUPERADMIN
from web.app import render
from web.charts import bars
from web.deps import require

router = APIRouter()
_bot_cache = {"ts": 0.0, "value": None}


async def bot_status(bot) -> dict:
    now = time.monotonic()
    if _bot_cache["value"] and now - _bot_cache["ts"] < 60:
        return _bot_cache["value"]
    try:
        t0 = time.perf_counter()
        me = await bot.get_me()
        value = {"ok": True, "username": me.username, "ping_ms": round((time.perf_counter() - t0) * 1000)}
    except Exception:
        value = {"ok": False, "username": None, "ping_ms": None}
    _bot_cache.update(ts=now, value=value)
    return value


@router.get("/monitoring")
async def monitoring(request: Request, user=Depends(require(ROLE_SUPERADMIN, ROLE_DIRECTOR))):
    m = await stats.monitoring()
    o = await stats.overview()
    overdue = await fetchall(
        """SELECT id, appeal_type, status, full_name, created_at FROM appeals
           WHERE status!='javob_berildi' AND created_at < datetime('now','-24 hours') ORDER BY id LIMIT 10"""
    )
    hours = bars([{"label": f"{h['h']:02d}", "n": h["n"]} for h in m["hours"]], height=170)
    up = m["uptime_s"]
    uptime = f"{up // 86400} д {up % 86400 // 3600} ч {up % 3600 // 60} мин" if up >= 86400 else f"{up // 3600} ч {up % 3600 // 60} мин"
    return render(request, "monitoring.html", m=m, o=o, overdue=overdue, hours=hours, uptime=uptime,
                  bot=await bot_status(request.app.state.bot))
