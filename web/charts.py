"""Графики рисуются на сервере как SVG-данные (без внешних библиотек и без inline-скриптов — работает под строгим CSP)."""
import math


def bars(series: list[dict], width=640, height=190, pad_l=28, pad_b=24, pad_t=12) -> dict:
    """series: [{'label': '12.05', 'n': 3}, ...] -> координаты столбцов + линии сетки."""
    peak = max([s["n"] for s in series] + [1])
    # «красивый» максимум оси
    step = 10 ** max(0, int(math.log10(peak)))
    top = int(math.ceil(peak / step) * step) if peak > 4 else max(peak, 4)
    plot_w, plot_h = width - pad_l - 8, height - pad_b - pad_t
    slot = plot_w / max(len(series), 1)
    bw = max(slot * 0.62, 2)
    out = []
    for i, s in enumerate(series):
        h = plot_h * s["n"] / top
        out.append({
            "x": round(pad_l + i * slot + (slot - bw) / 2, 1), "y": round(pad_t + plot_h - h, 1),
            "w": round(bw, 1), "h": round(max(h, 0), 1), "label": s["label"], "n": s["n"],
            "lx": round(pad_l + i * slot + slot / 2, 1),
            "show_label": (i % max(1, len(series) // 8) == 0) or i == len(series) - 1,
        })
    grid = [{"y": round(pad_t + plot_h - plot_h * k / 4, 1), "v": round(top * k / 4, 1) if top % 4 else top * k // 4}
            for k in range(5)]
    return {"w": width, "h": height, "bars": out, "grid": grid, "pad_l": pad_l, "label_y": height - 6}


def donut(parts: list[dict], radius=15.9155) -> list[dict]:
    """parts: [{'label','n','cls'}] -> сегменты для stroke-dasharray (окружность = 100)."""
    total = sum(p["n"] for p in parts) or 1
    offset, out = 25.0, []
    for p in parts:
        pct = p["n"] * 100 / total
        out.append({**p, "pct": round(pct, 1), "dash": f"{pct:.2f} {100 - pct:.2f}", "offset": round(offset, 2)})
        offset -= pct
    return out
