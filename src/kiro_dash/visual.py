"""Helpers visuais — barras horizontais e sparklines Unicode."""
from __future__ import annotations

_SPARK_CHARS = "▁▂▃▄▅▆▇█"


def bar_inline(pct: float, *, width: int = 20) -> str:
    """Barra horizontal Unicode. ``pct`` em [0, 1]; clampado."""
    pct = max(0.0, min(1.0, pct))
    filled = int(round(pct * width))
    return "█" * filled + "░" * (width - filled)


def sparkline(values: list[float], *, max_chars: int = 24) -> str:
    """Mini line chart Unicode. Lista vazia → string vazia."""
    if not values:
        return ""
    if len(values) > max_chars:
        values = values[-max_chars:]
    peak = max(values)
    low = min(values)
    if peak <= 0 or peak == low:
        return _SPARK_CHARS[0] * len(values)
    n = len(_SPARK_CHARS)
    out = []
    for v in values:
        if v <= 0:
            out.append(_SPARK_CHARS[0])
        else:
            idx = min(n - 1, int(round((v / peak) * (n - 1))))
            out.append(_SPARK_CHARS[idx])
    return "".join(out)
