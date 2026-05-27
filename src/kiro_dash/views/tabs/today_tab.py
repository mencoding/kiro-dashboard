"""Aba Today — agregado do dia local."""
from __future__ import annotations

from dataclasses import dataclass, field

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import DataTable, Static

from kiro_dash.aggregator import (
    Aggregate,
    AgentPairAgg,
    aggregate_by_agent_pair,
    aggregate_by_model,
    aggregate_by_project,
    aggregate_by_session,
    total_credits,
    turns_in_local_day,
)
from kiro_dash.config import load_aliases, default_config_path
from kiro_dash.models import Session
from kiro_dash.views.tabs._helpers import collect_for_tab, get_current_source


@dataclass(frozen=True, slots=True)
class TodaySnapshot:
    total_credits: float
    total_turns: int
    total_sessions: int
    by_model: list[Aggregate] = field(default_factory=list)
    by_agent_pair: list[AgentPairAgg] = field(default_factory=list)
    by_project: list[Aggregate] = field(default_factory=list)
    by_session: list[Aggregate] = field(default_factory=list)


def build_today_snapshot(sessions: list[Session]) -> TodaySnapshot:
    pairs = turns_in_local_day(sessions)
    aliases = load_aliases(default_config_path())
    return TodaySnapshot(
        total_credits=total_credits(pairs),
        total_turns=len(pairs),
        total_sessions=len({s.session_id for s, _ in pairs}),
        by_model=aggregate_by_model(pairs),
        by_agent_pair=aggregate_by_agent_pair(pairs),
        by_project=aggregate_by_project(pairs, aliases=aliases),
        by_session=aggregate_by_session(pairs),
    )


def _aggs_to_rows(aggs: list[Aggregate]) -> list[tuple[str, ...]]:
    return [
        (a.label, f"{a.credits:.2f}", str(a.turns), str(a.sessions))
        for a in aggs
    ]


def _aggs_to_rows_no_sessions(aggs: list[Aggregate]) -> list[tuple[str, ...]]:
    """Variante para a tabela 'Por sessão' — agrupamento 1:1, omite ``sessões``."""
    return [
        (a.label, f"{a.credits:.2f}", str(a.turns))
        for a in aggs
    ]


def _agent_pair_to_rows(aggs: list[AgentPairAgg]) -> list[tuple[str, ...]]:
    return [
        (a.runtime, a.persona, f"{a.credits:.2f}", str(a.turns), str(a.sessions))
        for a in aggs
    ]


class TodayTab(Container):
    def compose(self) -> ComposeResult:
        yield Static(id="today-header")
        with Horizontal():
            with Vertical():
                yield Static("[b]Por modelo[/b]")
                yield DataTable(id="today-models", zebra_stripes=True)
                yield Static("[b]Por agent (runtime × persona)[/b]")
                yield DataTable(id="today-agents", zebra_stripes=True)
            with Vertical():
                yield Static("[b]Por projeto[/b]")
                yield DataTable(id="today-projects", zebra_stripes=True)
                yield Static("[b]Por sessão[/b]")
                yield DataTable(id="today-sessions", zebra_stripes=True)

    def on_mount(self) -> None:
        # Tabelas com 4 colunas (label, créditos, turns, sessões)
        for tid in ("#today-models", "#today-projects"):
            t = self.query_one(tid, DataTable)
            t.add_columns("label", "créditos", "turns", "sessões")
        # Tabela "Por sessão" sem coluna sessões (1:1 — sempre 1)
        t = self.query_one("#today-sessions", DataTable)
        t.add_columns("label", "créditos", "turns")
        # Tabela de agent tem 5 colunas (runtime, persona, créditos, turns, sessões)
        t = self.query_one("#today-agents", DataTable)
        t.add_columns("runtime", "persona", "créditos", "turns", "sessões")
        self.refresh_snapshot()

    def refresh_snapshot(self) -> None:
        sessions = collect_for_tab(self)
        snap = build_today_snapshot(sessions)

        source = get_current_source(self)
        source_tag = f"[dim]·[/dim] [b]source={source}[/b] " if source != "all" else ""
        self.query_one("#today-header", Static).update(
            f"[b green]{snap.total_credits:.2f}[/b green] créditos  "
            f"[dim]{snap.total_turns} turns / {snap.total_sessions} sessões[/dim] "
            f"{source_tag}"
        )

        # Agregados de 4 colunas (label, créditos, turns, sessões)
        for tid, aggs in [
            ("#today-models", snap.by_model),
            ("#today-projects", snap.by_project),
        ]:
            t = self.query_one(tid, DataTable)
            t.clear()
            for row in _aggs_to_rows(aggs):
                t.add_row(*row)

        # "Por sessão": 3 colunas (label, créditos, turns)
        t = self.query_one("#today-sessions", DataTable)
        t.clear()
        for row in _aggs_to_rows_no_sessions(snap.by_session):
            t.add_row(*row)

        # Agent: 5 colunas
        t = self.query_one("#today-agents", DataTable)
        t.clear()
        for row in _agent_pair_to_rows(snap.by_agent_pair):
            t.add_row(*row)
