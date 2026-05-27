"""Aba Models — top modelos por créditos numa janela."""
from __future__ import annotations

from dataclasses import dataclass, field

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import DataTable, Static

from kiro_dash.aggregator import Aggregate, aggregate_by_model, turns_in_last_days
from kiro_dash.models import Session
from kiro_dash.parser import load_all_sessions


@dataclass(frozen=True, slots=True)
class ModelsSnapshot:
    window_days: int
    aggs: list[Aggregate] = field(default_factory=list)


def build_models_snapshot(sessions: list[Session], *, days: int = 7) -> ModelsSnapshot:
    pairs = turns_in_last_days(sessions, days=days)
    return ModelsSnapshot(window_days=days, aggs=aggregate_by_model(pairs))


class ModelsTab(Container):
    DEFAULT_DAYS = 7

    def compose(self) -> ComposeResult:
        yield Static(id="models-header")
        yield DataTable(id="models-table", zebra_stripes=True)

    def on_mount(self) -> None:
        t = self.query_one("#models-table", DataTable)
        t.add_columns("modelo", "créditos", "turns", "sessões", "duração")
        self.refresh_snapshot()

    def refresh_snapshot(self) -> None:
        sessions = load_all_sessions()
        snap = build_models_snapshot(sessions, days=self.DEFAULT_DAYS)
        self.query_one("#models-header", Static).update(
            f"[b]Modelos[/b] — últimos {snap.window_days}d"
        )
        t = self.query_one("#models-table", DataTable)
        t.clear()
        for a in snap.aggs:
            dur = int(a.duration.total_seconds())
            dur_str = f"{dur // 60}m" if dur < 3600 else f"{dur // 3600}h{(dur % 3600) // 60:02d}m"
            t.add_row(a.label, f"{a.credits:.2f}", str(a.turns), str(a.sessions), dur_str)
