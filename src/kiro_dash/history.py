"""Queries históricas — PeriodSummary e funções de agregação por período.

NOTA: Este módulo será substituído pela versão da Frente N no merge.
A Frente N é a implementação canônica; esta versão existe apenas para
desbloquear a Frente O (TUI History tab) em paralelo.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from kiro_dash.aggregator import total_credits, turns_in_local_day
from kiro_dash.snapshots import SnapshotPaths, read_snapshot


@dataclass(frozen=True, slots=True)
class PeriodSummary:
    """Sumário de um período (dia, semana, mês, ano)."""

    label: str
    credits: float
    turns: int
    sessions: int


def month_summary(
    year: int,
    month: int,
    *,
    paths: SnapshotPaths | None = None,
) -> PeriodSummary:
    """Agrega snapshots de todos os dias de um mês."""
    from calendar import monthrange

    _, last_day = monthrange(year, month)
    credits = 0.0
    turns = 0
    sessions = 0
    for day in range(1, last_day + 1):
        d = date(year, month, day)
        snap = read_snapshot(d, paths=paths)
        if snap:
            credits += snap["totals"]["credits"]
            turns += snap["totals"]["turns"]
            sessions += snap["totals"]["sessions"]
    return PeriodSummary(
        label=f"{year}-{month:02d}",
        credits=credits,
        turns=turns,
        sessions=sessions,
    )


def year_summary(
    year: int,
    *,
    paths: SnapshotPaths | None = None,
) -> PeriodSummary:
    """Agrega snapshots de todos os meses de um ano."""
    credits = 0.0
    turns = 0
    sessions = 0
    for month in range(1, 13):
        ms = month_summary(year, month, paths=paths)
        credits += ms.credits
        turns += ms.turns
        sessions += ms.sessions
    return PeriodSummary(
        label=str(year),
        credits=credits,
        turns=turns,
        sessions=sessions,
    )


def diff_summaries(a: PeriodSummary, b: PeriodSummary) -> dict:
    """Compara dois PeriodSummary. Retorna dict com deltas."""
    delta = a.credits - b.credits
    pct = (delta / b.credits) if b.credits > 0 else None
    return {
        "a_label": a.label,
        "b_label": b.label,
        "credits_a": a.credits,
        "credits_b": b.credits,
        "credits_delta": delta,
        "credits_pct": pct,
        "turns_a": a.turns,
        "turns_b": b.turns,
        "sessions_a": a.sessions,
        "sessions_b": b.sessions,
    }


def live_day_as_period(
    d: date,
    sessions: list | None = None,
    *,
    label: str | None = None,
    paths: SnapshotPaths | None = None,
) -> PeriodSummary:
    """Constrói PeriodSummary para um dia — usa snapshot se disponível."""
    snap = read_snapshot(d, paths=paths)
    if snap:
        return PeriodSummary(
            label=label or d.isoformat(),
            credits=snap["totals"]["credits"],
            turns=snap["totals"]["turns"],
            sessions=snap["totals"]["sessions"],
        )
    return PeriodSummary(label=label or d.isoformat(), credits=0.0, turns=0, sessions=0)


def live_window_as_period(
    start_day: date,
    days: int,
    *,
    label: str | None = None,
    paths: SnapshotPaths | None = None,
) -> PeriodSummary:
    """Agrega snapshots de uma janela de N dias a partir de start_day."""
    credits = 0.0
    turns = 0
    sessions = 0
    for offset in range(days):
        d = start_day + timedelta(days=offset)
        snap = read_snapshot(d, paths=paths)
        if snap:
            credits += snap["totals"]["credits"]
            turns += snap["totals"]["turns"]
            sessions += snap["totals"]["sessions"]
    return PeriodSummary(
        label=label or f"{start_day}+{days}d",
        credits=credits,
        turns=turns,
        sessions=sessions,
    )
