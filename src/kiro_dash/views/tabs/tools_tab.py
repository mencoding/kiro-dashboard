"""Aba Tools — breakdown de tool calls nas últimas N horas."""
from __future__ import annotations

from datetime import datetime, timezone

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import DataTable, Static

from kiro_dash.aggregator import aggregate_tools_in_window_by_source
from kiro_dash.parser import DEFAULT_SESSIONS_DIR
from kiro_dash.views.tabs._helpers import get_current_source
from kiro_dash.visual import bar_inline, sparkline


class ToolsTab(Container):
    DEFAULT_HOURS = 24

    def compose(self) -> ComposeResult:
        yield Static(id="tools-header")
        yield DataTable(id="tools-table", zebra_stripes=True, cursor_type="row")
        yield Static(id="tools-detail")

    def on_mount(self) -> None:
        t = self.query_one("#tools-table", DataTable)
        t.add_columns("tool", "count", "share", "sessões", "erros")
        self._tools_by_index: list[str] = []
        self.refresh_snapshot()

    def refresh_snapshot(self) -> None:
        source = get_current_source(self)
        aggs = aggregate_tools_in_window_by_source(
            source, sessions_dir=DEFAULT_SESSIONS_DIR, hours=self.DEFAULT_HOURS
        )
        total = sum(a["count"] for a in aggs)
        err_total = sum(a["errors"] for a in aggs)
        source_tag = f"  [dim]·[/dim] [b]source={source}[/b]" if source != "all" else ""
        self.query_one("#tools-header", Static).update(
            f"[b]Tools[/b] — últimas {self.DEFAULT_HOURS}h{source_tag}  "
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

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        row_idx = event.cursor_row
        if not (0 <= row_idx < len(self._tools_by_index)):
            return
        self._render_detail(self._tools_by_index[row_idx])

    def _render_detail(self, name: str) -> None:
        from kiro_dash.cli import collect_recent_tools

        calls = [t for t in collect_recent_tools(hours=self.DEFAULT_HOURS) if t.name == name]
        errors = [t for t in calls if (t.status or "").lower() == "error"][:5]

        hours_buckets = [0] * 24
        now = datetime.now(timezone.utc)
        for t in calls:
            # ToolCall doesn't have timestamp, use bucket 0 as fallback
            pass
        # Since ToolCall has no timestamp, show flat sparkline based on count
        n_err = sum(1 for t in calls if (t.status or "").lower() == "error")

        lines = [
            f"[b]{name}[/b]  {len(calls)} chamadas / {n_err} erros",
            "",
        ]
        if errors:
            lines.append("[bold red]Erros recentes:[/bold red]")
            for t in errors:
                lines.append(
                    f"  {t.tool_use_id[:8]}  [red]{t.error_summary or '?'}[/red]"
                )
        else:
            lines.append("[green]Sem erros nas últimas 24h.[/green]")
        self.query_one("#tools-detail", Static).update("\n".join(lines))
