"""Aba History — série temporal + comparativos (sparklines 30d/12m + grid 2×2)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Static

from kiro_dash.history import (
    PeriodSummary,
    diff_summaries,
    live_day_as_period,
    live_window_as_period,
    month_summary,
)
from kiro_dash.snapshots import read_snapshot
from kiro_dash.visual import bar_inline, sparkline


@dataclass(frozen=True, slots=True)
class HistorySnapshot:
    daily_30d: list[float] = field(default_factory=list)
    monthly_12: list[float] = field(default_factory=list)
    today_vs_yesterday: dict | None = None
    week_vs_lastweek: dict | None = None
    month_vs_lastmonth: dict | None = None
    year_vs_lastyear: dict | None = None


def build_history_snapshot() -> HistorySnapshot:
    """Constrói snapshot completo para a aba History."""
    today = datetime.now().astimezone().date()

    # 30 dias diários
    daily = []
    for offset in range(29, -1, -1):
        d = today - timedelta(days=offset)
        snap = read_snapshot(d)
        daily.append(snap["totals"]["credits"] if snap else 0.0)

    # 12 meses
    monthly = []
    cursor = today.replace(day=1)
    months_back: list[tuple[int, int]] = []
    for _ in range(12):
        months_back.append((cursor.year, cursor.month))
        if cursor.month == 1:
            cursor = cursor.replace(year=cursor.year - 1, month=12)
        else:
            cursor = cursor.replace(month=cursor.month - 1)
    months_back.reverse()
    for y, m in months_back:
        s = month_summary(y, m)
        monthly.append(s.credits)

    # Comparativos
    a_today = live_day_as_period(today, label="hoje")
    b_yesterday = live_day_as_period(today - timedelta(days=1), label="ontem")
    todvy = diff_summaries(a_today, b_yesterday)

    week_start = today - timedelta(days=6)
    a_week = live_window_as_period(week_start, days=7, label="última semana")
    prev_week_start = week_start - timedelta(days=7)
    b_week = live_window_as_period(prev_week_start, days=7, label="semana anterior")
    weekvw = diff_summaries(a_week, b_week)

    cur_m = month_summary(today.year, today.month)
    prev_m_date = today.replace(day=1) - timedelta(days=1)
    prev_m = month_summary(prev_m_date.year, prev_m_date.month)
    monvm = diff_summaries(cur_m, prev_m)

    from kiro_dash.history import year_summary

    cur_y = year_summary(today.year)
    prev_y = year_summary(today.year - 1)
    yrvy = diff_summaries(cur_y, prev_y)

    return HistorySnapshot(
        daily_30d=daily,
        monthly_12=monthly,
        today_vs_yesterday=todvy,
        week_vs_lastweek=weekvw,
        month_vs_lastmonth=monvm,
        year_vs_lastyear=yrvy,
    )


def _render_cmp(diff: dict | None, title: str) -> str:
    if diff is None:
        return f"[b]{title}[/b]\n[dim]sem dados[/dim]"
    a, b = diff["a_label"], diff["b_label"]
    cred_a, cred_b = diff["credits_a"], diff["credits_b"]
    delta = diff["credits_delta"]
    pct = diff.get("credits_pct")
    delta_style = "green" if delta >= 0 else "red"
    pct_str = f" ({pct * 100:+.1f}%)" if pct is not None else ""
    bar = bar_inline(min(1.0, abs(delta) / max(cred_a, cred_b, 1)), width=14)
    return (
        f"[b]{title}[/b]\n"
        f"  {a:<14}: {cred_a:>8.2f}\n"
        f"  {b:<14}: {cred_b:>8.2f}\n"
        f"  Δ: [{delta_style}]{delta:+.2f}[/{delta_style}]{pct_str}\n"
        f"  {bar}"
    )


class HistoryTab(Container):
    """Aba History — série temporal + 4 comparativos."""

    def compose(self) -> ComposeResult:
        yield Static(id="history-header")
        yield Static(id="history-spark30")
        yield Static(id="history-spark12m")
        with Horizontal(id="history-compare-row1"):
            yield Static(id="cmp-today", classes="cmp-card")
            yield Static(id="cmp-week", classes="cmp-card")
        with Horizontal(id="history-compare-row2"):
            yield Static(id="cmp-month", classes="cmp-card")
            yield Static(id="cmp-year", classes="cmp-card")

    def on_mount(self) -> None:
        self.refresh_snapshot()

    def refresh_snapshot(self) -> None:
        snap = build_history_snapshot()
        self.query_one("#history-header", Static).update(
            "[b]Histórico[/b] — séries temporais e comparativos "
            "[dim](pressione 'r' para atualizar)[/dim]"
        )

        spark30 = sparkline(snap.daily_30d, max_chars=30)
        peak_30 = max(snap.daily_30d) if snap.daily_30d else 0
        self.query_one("#history-spark30", Static).update(
            f"[b]30 dias[/b] (créditos/dia, pico {peak_30:.0f}):\n  {spark30}"
        )

        spark12 = sparkline(snap.monthly_12, max_chars=12)
        peak_12 = max(snap.monthly_12) if snap.monthly_12 else 0
        self.query_one("#history-spark12m", Static).update(
            f"[b]12 meses[/b] (créditos/mês, pico {peak_12:.0f}):\n  {spark12}"
        )

        self.query_one("#cmp-today", Static).update(
            _render_cmp(snap.today_vs_yesterday, "Hoje × Ontem")
        )
        self.query_one("#cmp-week", Static).update(
            _render_cmp(snap.week_vs_lastweek, "Semana × Sem. anterior")
        )
        self.query_one("#cmp-month", Static).update(
            _render_cmp(snap.month_vs_lastmonth, "Mês × Mês anterior")
        )
        self.query_one("#cmp-year", Static).update(
            _render_cmp(snap.year_vs_lastyear, "Ano × Ano anterior")
        )
