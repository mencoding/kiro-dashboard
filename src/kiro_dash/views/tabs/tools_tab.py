"""Aba Tools — breakdown de tool calls nas últimas N horas."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import DataTable, Static

from kiro_dash.aggregator import aggregate_tools_in_window
from kiro_dash.parser import DEFAULT_SESSIONS_DIR
from kiro_dash.visual import bar_inline


class ToolsTab(Container):
    DEFAULT_HOURS = 24

    def compose(self) -> ComposeResult:
        yield Static(id="tools-header")
        yield DataTable(id="tools-table", zebra_stripes=True, cursor_type="row")
        yield Static(id="tools-detail")

    def on_mount(self) -> None:
        t = self.query_one("#tools-table", DataTable)
        t.add_columns("tool", "count", "share", "sessões", "erros")
        self.refresh_snapshot()

    def refresh_snapshot(self) -> None:
        aggs = aggregate_tools_in_window(DEFAULT_SESSIONS_DIR, hours=self.DEFAULT_HOURS)
        total = sum(a["count"] for a in aggs)
        err_total = sum(a["errors"] for a in aggs)
        self.query_one("#tools-header", Static).update(
            f"[b]Tools[/b] — últimas {self.DEFAULT_HOURS}h  "
            f"[cyan]{total} chamadas[/cyan]  "
            + (f"[red]{err_total} erros[/red]" if err_total else "")
        )
        t = self.query_one("#tools-table", DataTable)
        t.clear()
        self._tools_by_index = [a["name"] for a in aggs]
        for a in aggs:
            pct = a["count"] / total if total else 0
            bar = f"{bar_inline(pct, width=15)} {pct*100:5.1f}%"
            err_text = f"[red]{a['errors']}[/red]" if a["errors"] else "[dim]0[/dim]"
            t.add_row(a["name"], str(a["count"]), bar, str(a["sessions"]), err_text)
