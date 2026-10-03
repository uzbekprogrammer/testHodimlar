import os
import time

from config import DB_PATH
from database.db import fetchall, fetchone, scalar

STARTED_AT = time.time()
_cache: dict[str, tuple[float, object]] = {}
TASHKENT = "'+5 hours'"


async def _cached(key: str, ttl: float, fn):
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    value = await fn()
    _cache[key] = (now, value)
    return value


def invalidate():
    _cache.clear()


async def _overview():
    row = await fetchone(
        f"""
        SELECT COUNT(*) AS total,
               SUM(status='yangi') AS new,
               SUM(status='v_rabote') AS in_work,
               SUM(status='javob_berildi') AS answered,
               SUM(appeal_type='corruption') AS corruption,
               SUM(appeal_type='personal') AS personal,
               SUM(appeal_type='taklif') AS proposal,
               SUM(date(created_at,{TASHKENT}) = date('now',{TASHKENT})) AS today,
               SUM(status!='javob_berildi' AND created_at < datetime('now','-24 hours')) AS overdue,
               AVG(CASE WHEN answered_at IS NOT NULL
                        THEN (julianday(answered_at)-julianday(created_at))*24 END) AS avg_hours
        FROM appeals
        """
    )
    row = {k: (v or 0) for k, v in row.items()}
    row["avg_hours"] = round(row["avg_hours"], 1)
    row["users"] = await scalar("SELECT COUNT(*) FROM users")
    appt = await fetchone(
        f"""SELECT SUM(status='kutilmoqda') AS pending,
                   SUM(status='tasdiqlandi' AND appointment_date >= date('now',{TASHKENT})) AS upcoming,
                   COUNT(*) AS total FROM appointments"""
    )
    row["appt_pending"] = appt["pending"] or 0
    row["appt_upcoming"] = appt["upcoming"] or 0
    row["appt_total"] = appt["total"] or 0
    return row


async def overview():
    return await _cached("overview", 5, _overview)


async def _daily(days: int = 14):
    rows = await fetchall(
        f"""SELECT date(created_at,{TASHKENT}) AS d, COUNT(*) AS n FROM appeals
            WHERE created_at >= datetime('now', ?) GROUP BY d""",
        (f"-{days} days",),
    )
    by_day = {r["d"]: r["n"] for r in rows}
    out = await fetchall(
        f"""WITH RECURSIVE r(i) AS (SELECT 0 UNION ALL SELECT i+1 FROM r WHERE i < ?)
            SELECT date('now',{TASHKENT}, '-'||i||' days') AS d FROM r ORDER BY d""",
        (days - 1,),
    )
    return [{"d": r["d"], "n": by_day.get(r["d"], 0)} for r in out]


async def daily(days: int = 14):
    return await _cached(f"daily{days}", 30, lambda: _daily(days))


async def _monitoring():
    responders = await fetchall(
        """SELECT COALESCE(answered_by,'—') AS who, COUNT(*) AS n,
                  ROUND(AVG((julianday(answered_at)-julianday(created_at))*24),1) AS avg_h
           FROM appeals WHERE status='javob_berildi' AND answered_at IS NOT NULL GROUP BY who ORDER BY n DESC"""
    )
    sla = await fetchone(
        """SELECT SUM(status!='javob_berildi' AND created_at >= datetime('now','-4 hours')) AS fresh,
                  SUM(status!='javob_berildi' AND created_at < datetime('now','-4 hours')
                      AND created_at >= datetime('now','-24 hours')) AS warn,
                  SUM(status!='javob_berildi' AND created_at < datetime('now','-24 hours')) AS overdue
           FROM appeals"""
    )
    hours = await fetchall(
        f"""SELECT CAST(strftime('%H', created_at, {TASHKENT}) AS INTEGER) AS h, COUNT(*) AS n
            FROM appeals GROUP BY h"""
    )
    hmap = {r["h"]: r["n"] for r in hours}
    departments = await fetchall(
        """SELECT COALESCE(NULLIF(u.department,''),'Не указан') AS dep, COUNT(*) AS n
           FROM appeals a LEFT JOIN users u ON u.telegram_id=a.telegram_id
           WHERE a.appeal_type != 'corruption' GROUP BY dep ORDER BY n DESC LIMIT 8"""
    )
    return {
        "responders": responders,
        "sla": {k: (v or 0) for k, v in sla.items()},
        "hours": [{"h": h, "n": hmap.get(h, 0)} for h in range(24)],
        "departments": departments,
        "audit_24h": await scalar("SELECT COUNT(*) FROM audit_log WHERE ts >= datetime('now','-24 hours')"),
        "failed_logins_24h": await scalar(
            "SELECT COUNT(*) FROM audit_log WHERE action='login_failed' AND ts >= datetime('now','-24 hours')"
        ),
        "sessions": await scalar("SELECT COUNT(*) FROM web_sessions"),
        "db_size_mb": round(os.path.getsize(DB_PATH) / 1048576, 2) if os.path.exists(DB_PATH) else 0,
        "uptime_s": int(time.time() - STARTED_AT),
    }


async def monitoring():
    return await _cached("monitoring", 10, _monitoring)
