from datetime import datetime, timedelta

TZ_OFFSET = timedelta(hours=5)   # Asia/Tashkent (UTC+5)


def to_local(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value[:19], "%Y-%m-%d %H:%M:%S") + TZ_OFFSET
    except ValueError:
        return None


def fmt_dt(value: str | None) -> str:
    dt = to_local(value)
    return dt.strftime("%d.%m.%Y %H:%M") if dt else "—"


def fmt_ago(value: str | None) -> str:
    dt = to_local(value)
    if not dt:
        return "—"
    secs = int((datetime.utcnow() + TZ_OFFSET - dt).total_seconds())
    if secs < 60:
        return "только что"
    if secs < 3600:
        return f"{secs // 60} мин назад"
    if secs < 86400:
        return f"{secs // 3600} ч назад"
    return f"{secs // 86400} дн назад"
