"""Reconstrução de resumos por período via cascata de snapshots diários."""
from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from kiro_dash.snapshots import SnapshotPaths, read_snapshot


@dataclass(frozen=True, slots=True)
class PeriodSummary:
    period_label: str
    credits: float
    turns: int
    sessions: int
    days_with_data: int
    by_model: list[dict] = field(default_factory=list)
    by_project: list[dict] = field(default_factory=list)
    by_tool: list[dict] = field(default_factory=list)


def _aggregate_breakdown(snaps: list[dict], key: str) -> list[dict]:
    """Re-agrega ``by_X`` somando entries com mesmo label."""
    label_field = "name" if key == "by_tool" else "label"
    bucket: dict[str, dict] = defaultdict(
        lambda: {"credits": 0.0, "turns": 0, "sessions": 0,
                 "duration_secs": 0, "tool_uses": 0, "count": 0, "errors": 0}
    )
    for snap in snaps:
        for item in snap.get(key, []):
            label = item.get(label_field, "?")
            for f in ("credits", "turns", "sessions", "duration_secs",
                      "tool_uses", "count", "errors"):
                if f in item:
                    bucket[label][f] = bucket[label].get(f, 0) + item[f]
    out = []
    for label, vals in bucket.items():
        entry = {label_field: label}
        entry.update({k: v for k, v in vals.items() if v != 0})
        out.append(entry)
    out.sort(key=lambda x: x.get("credits", x.get("count", 0)), reverse=True)
    return out


def _build_summary(snaps: list[dict], *, label: str) -> PeriodSummary:
    if not snaps:
        return PeriodSummary(period_label=label, credits=0, turns=0,
                             sessions=0, days_with_data=0)
    return PeriodSummary(
        period_label=label,
        credits=round(sum(s["totals"]["credits"] for s in snaps), 4),
        turns=sum(s["totals"]["turns"] for s in snaps),
        sessions=sum(s["totals"]["sessions"] for s in snaps),
        days_with_data=len(snaps),
        by_model=_aggregate_breakdown(snaps, "by_model"),
        by_project=_aggregate_breakdown(snaps, "by_project"),
        by_tool=_aggregate_breakdown(snaps, "by_tool"),
    )


def month_summary(
    year: int, month: int, *, paths: SnapshotPaths | None = None,
) -> PeriodSummary:
    """Soma todos os snapshots disponíveis do mês."""
    days_in_month = calendar.monthrange(year, month)[1]
    snaps = []
    for d in range(1, days_in_month + 1):
        snap = read_snapshot(date(year, month, d), paths=paths)
        if snap is not None:
            snaps.append(snap)
    return _build_summary(snaps, label=f"{year:04d}-{month:02d}")


def year_summary(
    year: int, *, paths: SnapshotPaths | None = None,
) -> PeriodSummary:
    """Soma todos os snapshots disponíveis do ano."""
    snaps = []
    d = date(year, 1, 1)
    while d.year == year:
        snap = read_snapshot(d, paths=paths)
        if snap is not None:
            snaps.append(snap)
        d += timedelta(days=1)
    return _build_summary(snaps, label=str(year))


def diff_summaries(a: PeriodSummary, b: PeriodSummary) -> dict[str, Any]:
    """Compara ``a`` vs ``b``. Retorna dict com deltas e percentuais."""
    def pct(a_v, b_v):
        return (a_v - b_v) / b_v if b_v != 0 else None

    return {
        "a_label": a.period_label,
        "b_label": b.period_label,
        "credits_a": a.credits,
        "credits_b": b.credits,
        "credits_delta": a.credits - b.credits,
        "credits_pct": pct(a.credits, b.credits),
        "turns_delta": a.turns - b.turns,
        "turns_pct": pct(a.turns, b.turns),
        "sessions_delta": a.sessions - b.sessions,
        "days_a": a.days_with_data,
        "days_b": b.days_with_data,
    }


def live_day_as_period(d: date, *, label: str) -> PeriodSummary:
    """Constrói PeriodSummary lendo turns live de um dia (D ou D-1)."""
    from kiro_dash.aggregator import total_credits, turns_in_local_day
    from kiro_dash.parser import load_all_sessions

    sessions = load_all_sessions()
    pairs = turns_in_local_day(sessions, d)
    return PeriodSummary(
        period_label=label,
        credits=round(total_credits(pairs), 4),
        turns=len(pairs),
        sessions=len({s.session_id for s, _ in pairs}),
        days_with_data=1 if pairs else 0,
    )


def live_window_as_period(
    start_day: date, *, days: int, label: str,
) -> PeriodSummary:
    """PeriodSummary acumulado em janela contígua (live se hoje/ontem; snapshot caso contrário)."""
    from kiro_dash.aggregator import total_credits, turns_in_local_day
    from kiro_dash.parser import load_all_sessions

    today_local = datetime.now().astimezone().date()
    sessions = load_all_sessions()

    total_cred = 0.0
    total_turns = 0
    total_sessions = 0
    days_with = 0

    for offset in range(days):
        d = start_day + timedelta(days=offset)
        # Live para hoje e ontem; snapshot para o resto
        if d >= today_local - timedelta(days=1):
            pairs = turns_in_local_day(sessions, d)
            if pairs:
                total_cred += total_credits(pairs)
                total_turns += len(pairs)
                total_sessions += len({s.session_id for s, _ in pairs})
                days_with += 1
        else:
            snap = read_snapshot(d)
            if snap is not None:
                total_cred += snap["totals"]["credits"]
                total_turns += snap["totals"]["turns"]
                total_sessions += snap["totals"]["sessions"]
                days_with += 1

    return PeriodSummary(
        period_label=label,
        credits=round(total_cred, 4),
        turns=total_turns,
        sessions=total_sessions,
        days_with_data=days_with,
    )


def resolve_period(s: str) -> PeriodSummary | None:
    """Converte string ('2026-05', 'today', 'week', etc.) em PeriodSummary.

    Exported for use by other modules (e.g., TUI history tab).
    """
    s = s.strip().lower()
    today = datetime.now().astimezone().date()

    if s == "today":
        return live_day_as_period(today, label="hoje")
    if s == "yesterday":
        return live_day_as_period(today - timedelta(days=1), label="ontem")
    if s == "week":
        start = today - timedelta(days=6)
        return live_window_as_period(start, days=7, label="última semana")
    if s == "last-week":
        start = today - timedelta(days=13)
        return live_window_as_period(start, days=7, label="semana anterior")
    if s == "month":
        return month_summary(today.year, today.month)
    if s == "last-month":
        prev = today.replace(day=1) - timedelta(days=1)
        return month_summary(prev.year, prev.month)
    if s == "year":
        return year_summary(today.year)
    if s == "last-year":
        return year_summary(today.year - 1)

    # YYYY-MM
    if len(s) == 7 and s[4] == "-":
        try:
            year, m = int(s[:4]), int(s[5:])
            if 1 <= m <= 12:
                return month_summary(year, m)
        except ValueError:
            pass
        return None
    # YYYY
    if len(s) == 4 and s.isdigit():
        return year_summary(int(s))

    return None
