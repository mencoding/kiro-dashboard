"""Widget da aba Now — sessões ativas com auto-refresh + card de saldo IDE."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import DataTable, Static

from kiro_dash.aggregator import active_sessions, total_credits, turns_in_local_day
from kiro_dash.backends.ide_state import IdeStateError
from kiro_dash.freshness import format_age, freshness_for
from kiro_dash.models import Session
from kiro_dash.sources import Sources
from kiro_dash.views.tabs._helpers import collect_for_tab, get_current_source
from kiro_dash.visual import bar_inline


def _build_balance_card(sources: Sources | None = None) -> str:
    """Renderiza card de saldo IDE (T2-W8). String vazia se IDE indisponível.

    Layout:
        ╭─ Saldo Kiro IDE [verde · 47s atrás] ─╮
        │ 1598 / 10000  (15.99%)               │
        │ ████░░░░░░░░░░░░░░░░░░░░░░░░░░░ 15%  │
        │ Reset: 2026-06-15  ·  Overage: 0.00$ │
        ╰──────────────────────────────────────╯
    """
    s = sources if sources is not None else Sources.detect()
    if s.ide_state is None:
        return ""
    try:
        state = s.ide_state.read_usage_state()  # type: ignore[attr-defined]
    except IdeStateError:
        return ""
    if state is None:
        return ""

    age = state.age_seconds
    level = freshness_for(age)
    age_str = format_age(age)
    pct = state.percentage_used / 100.0
    bar = bar_inline(pct, width=30)

    # Cor da % conforme threshold de uso (não confundir com freshness)
    if state.percentage_used >= 95:
        pct_color = "red"
    elif state.percentage_used >= 80:
        pct_color = "yellow"
    else:
        pct_color = "green"

    reset_str = state.reset_date.astimezone().strftime("%Y-%m-%d")
    overage_str = (
        f"[red]{state.overage_charges:.2f} {state.currency_code}[/red]"
        if state.overage_charges > 0
        else f"[dim]{state.overage_charges:.2f} {state.currency_code}[/dim]"
    )

    lines = [
        f"[b]Saldo Kiro IDE[/b]  [{level.value}]\\[{level.value} · {age_str} atrás][/{level.value}]",
        f"  [b]{state.current_usage:.0f}[/b] / {state.usage_limit:.0f}  "
        f"([{pct_color}]{state.percentage_used:.2f}%[/{pct_color}])",
        f"  {bar}  [{pct_color}]{state.percentage_used:5.1f}%[/{pct_color}]",
        f"  Reset: [b]{reset_str}[/b]  ·  Overage: {overage_str}",
    ]
    return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class NowSnapshot:
    active_count: int
    today_credits: float
    timestamp: datetime
    rows: list[tuple[str, ...]] = field(default_factory=list)


def build_now_snapshot(sessions: list[Session]) -> NowSnapshot:
    actives = active_sessions(sessions)
    actives.sort(key=lambda s: s.last_turn_at or s.updated_at, reverse=True)

    today_pairs = turns_in_local_day(sessions)
    today_total = total_credits(today_pairs)

    rows: list[tuple[str, ...]] = []
    for s in actives:
        last = s.last_turn_at or s.updated_at
        delta = (datetime.now(timezone.utc) - last).total_seconds()
        if delta < 60:
            ago = f"{int(delta)}s"
        elif delta < 3600:
            ago = f"{int(delta // 60)}m"
        else:
            ago = f"{int(delta // 3600)}h"
        rows.append((
            s.session_id[:8],
            s.agent_name or "?",
            s.model_id,
            s.cwd or "—",
            str(len(s.turns)),
            f"{s.total_credits:.2f}",
            f"{s.last_context_usage_pct:.1f}",
            ago,
        ))

    return NowSnapshot(
        active_count=len(actives),
        today_credits=today_total,
        timestamp=datetime.now().astimezone(),
        rows=rows,
    )


class NowTab(Container):
    """Aba Now — sessões ativas com auto-refresh + card de saldo.

    Apenas esta aba tem set_interval; demais são snapshot manual.
    Card de saldo (T2-W8) aparece no topo se IDE detectado;
    oculto se IDE indisponível.
    """

    NOW_REFRESH_SEC: float = 2.0

    def compose(self) -> ComposeResult:
        yield Static(id="now-balance-card")
        yield Static(id="now-header")
        yield DataTable(id="now-table", zebra_stripes=True)

    def on_mount(self) -> None:
        table = self.query_one("#now-table", DataTable)
        table.add_columns("sid", "agent", "modelo", "cwd", "turns", "créditos", "ctx %", "último")
        self.refresh_snapshot()
        self.set_interval(self.NOW_REFRESH_SEC, self.refresh_snapshot)

    def refresh_snapshot(self) -> None:
        sessions = collect_for_tab(self)
        snap = build_now_snapshot(sessions)
        source = get_current_source(self)

        # Balance card (T2-W8)
        balance_text = _build_balance_card()
        balance_widget = self.query_one("#now-balance-card", Static)
        if balance_text:
            balance_widget.update(balance_text)
            balance_widget.display = True
        else:
            balance_widget.update("")
            balance_widget.display = False

        source_tag = f"[dim]·[/dim] [b]source={source}[/b] " if source != "all" else ""
        header = self.query_one("#now-header", Static)
        header.update(
            f"[b]{snap.active_count}[/b] sessões ativas — "
            f"hoje: [b green]{snap.today_credits:.2f}[/b green] créditos "
            f"{source_tag}"
            f"([dim]{snap.timestamp.strftime('%H:%M:%S')}[/dim])"
        )

        table = self.query_one("#now-table", DataTable)
        table.clear()
        for row in snap.rows:
            table.add_row(*row)
