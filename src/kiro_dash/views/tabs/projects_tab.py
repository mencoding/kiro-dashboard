"""Aba Projects — top projetos por créditos numa janela."""
from __future__ import annotations

from dataclasses import dataclass, field

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import DataTable, Static

from kiro_dash.aggregator import Aggregate, aggregate_by_project, turns_in_last_days
from kiro_dash.models import Session
from kiro_dash.views.tabs._helpers import collect_for_tab, get_current_source


@dataclass(frozen=True, slots=True)
class ProjectsSnapshot:
    window_days: int
    aggs: list[Aggregate] = field(default_factory=list)


def build_projects_snapshot(sessions: list[Session], *, days: int = 7) -> ProjectsSnapshot:
    pairs = turns_in_last_days(sessions, days=days)
    return ProjectsSnapshot(window_days=days, aggs=aggregate_by_project(pairs))


class ProjectsTab(Container):
    DEFAULT_DAYS = 7

    def compose(self) -> ComposeResult:
        yield Static(id="projects-header")
        yield DataTable(id="projects-table", zebra_stripes=True)

    def on_mount(self) -> None:
        t = self.query_one("#projects-table", DataTable)
        t.add_columns("projeto", "créditos", "turns", "sessões", "duração")
        self.refresh_snapshot()

    def refresh_snapshot(self) -> None:
        sessions = collect_for_tab(self)
        snap = build_projects_snapshot(sessions, days=self.DEFAULT_DAYS)
        source = get_current_source(self)
        source_tag = f"  [dim]·[/dim] [b]source={source}[/b]" if source != "all" else ""
        self.query_one("#projects-header", Static).update(
            f"[b]Projetos[/b] — últimos {snap.window_days}d{source_tag}"
        )
        t = self.query_one("#projects-table", DataTable)
        t.clear()
        for a in snap.aggs:
            dur = int(a.duration.total_seconds())
            dur_str = f"{dur // 60}m" if dur < 3600 else f"{dur // 3600}h{(dur % 3600) // 60:02d}m"
            t.add_row(a.label, f"{a.credits:.2f}", str(a.turns), str(a.sessions), dur_str)
