"""Help modal completo da TUI (T6-W8).

ModalScreen Textual mostrando lista completa de atalhos com descrição
+ contexto. Aberto via ``?`` e fechado via ``ESC`` ou ``q``.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Static


_BINDINGS_TABLE: list[tuple[str, str, str]] = [
    # (tecla, ação, contexto)
    ("1", "Now", "sessões ativas + saldo + auto-refresh 2s"),
    ("2", "Today", "agregado do dia em 4 cards"),
    ("3", "Projects", "top projetos por créditos (7d)"),
    ("4", "Models", "top modelos por créditos (7d)"),
    ("5", "Tools", "breakdown de tool calls (24h)"),
    ("6", "Session", "drill-down por session_id (TODO)"),
    ("7", "History", "snapshots históricos + sparklines"),
    ("r", "Refresh", "recarrega dados da aba ativa"),
    ("s", "Source", "cycle: all → cli → ide → all"),
    ("?", "Ajuda", "este modal"),
    ("q", "Sair", "fecha a TUI ou o modal aberto"),
]


class HelpModal(ModalScreen):
    """Modal com tabela de atalhos. ESC/q fecha."""

    BINDINGS = [
        Binding("escape", "dismiss", "Fechar"),
        Binding("q", "dismiss", "Fechar"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="help-modal-body"):
            yield Static(
                "[b]kiro-dash — atalhos[/b]\n\n"
                "[dim]ESC ou q para fechar[/dim]",
                id="help-title",
            )
            yield DataTable(id="help-table", show_header=True, header_style="bold")
            yield Static(
                "[dim]filtro de fonte (s) afeta as abs Now/Today/Projects/"
                "Models/Tools — não afeta Session/History.[/dim]",
                id="help-footer",
            )

    def on_mount(self) -> None:
        t = self.query_one("#help-table", DataTable)
        t.add_columns("tecla", "ação", "contexto")
        for key, action, context in _BINDINGS_TABLE:
            t.add_row(key, action, context)
        t.cursor_type = "none"
