"""Widget da aba Now — sessões ativas com auto-refresh."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import DataTable, Static

from kiro_dash.aggregator import active_sessions, total_credits, turns_in_local_day
from kiro_dash.models import Session
from kiro_dash.parser import load_all_sessions


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
    """Aba Now — sessões ativas com auto-refresh.

    Apenas esta aba tem set_interval; demais são snapshot manual.
    """

    NOW_REFRESH_SEC: float = 2.0

    def compose(self) -> ComposeResult:
        yield Static(id="now-header")
        yield DataTable(id="now-table", zebra_stripes=True)

    def on_mount(self) -> None:
        table = self.query_one("#now-table", DataTable)
        table.add_columns("sid", "agent", "modelo", "cwd", "turns", "créditos", "ctx %", "último")
        self.refresh_snapshot()
        self.set_interval(self.NOW_REFRESH_SEC, self.refresh_snapshot)

    def refresh_snapshot(self) -> None:
        sessions = load_all_sessions()
        snap = build_now_snapshot(sessions)

        header = self.query_one("#now-header", Static)
        header.update(
            f"[b]{snap.active_count}[/b] sessões ativas — "
            f"hoje: [b green]{snap.today_credits:.2f}[/b green] créditos "
            f"([dim]{snap.timestamp.strftime('%H:%M:%S')}[/dim])"
        )

        table = self.query_one("#now-table", DataTable)
        table.clear()
        for row in snap.rows:
            table.add_row(*row)
