"""Aba Session — lista todas as sessões; Enter abre drill-down inline."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.widgets import DataTable, Static

from kiro_dash.parser import discover_sessions, load_session_file


class SessionTab(Container):
    def compose(self) -> ComposeResult:
        yield Static(id="session-header")
        with Vertical():
            yield DataTable(id="session-list", zebra_stripes=True, cursor_type="row")
            yield Static(id="session-details")

    def on_mount(self) -> None:
        t = self.query_one("#session-list", DataTable)
        t.add_columns("sid", "agent", "modelo", "turns", "créditos", "atualizada")
        self.refresh_snapshot()

    def refresh_snapshot(self) -> None:
        paths = discover_sessions()
        sessions = []
        for p in paths:
            s = load_session_file(p)
            if s is not None:
                sessions.append(s)

        self.query_one("#session-header", Static).update(
            f"[b]{len(sessions)}[/b] sessões — selecione com ↑/↓, Enter para drill-down"
        )
        t = self.query_one("#session-list", DataTable)
        t.clear()
        self._sessions_by_index = sessions
        for s in sessions:
            sid = f"{s.session_id[:8]}{' ●' if s.is_active else ''}"
            t.add_row(
                sid,
                s.agent_name or "?",
                s.model_id,
                str(len(s.turns)),
                f"{s.total_credits:.2f}",
                s.updated_at.astimezone().strftime("%Y-%m-%d %H:%M"),
            )
        self.query_one("#session-details", Static).update("")

    def on_data_table_row_selected(self, event) -> None:  # type: ignore[no-untyped-def]
        idx = event.cursor_row
        if not (0 <= idx < len(self._sessions_by_index)):
            return
        s = self._sessions_by_index[idx]
        lines = [
            f"[b]{s.session_id}[/b]",
            f"título: {s.title or '—'}",
            f"agent: {s.agent_name}  modelo: {s.model_id} (×{s.rate_multiplier})",
            f"cwd: {s.cwd}",
            f"turns: {len(s.turns)}  créditos: {s.total_credits:.2f}  ctx final: {s.last_context_usage_pct:.1f}%",
            f"criada: {s.created_at.astimezone().isoformat(timespec='seconds')}",
            f"atualizada: {s.updated_at.astimezone().isoformat(timespec='seconds')}",
        ]
        self.query_one("#session-details", Static).update("\n".join(lines))
