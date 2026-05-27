"""Helpers compartilhados para tabs da TUI (Wave 8).

Acesso uniforme a ``self.app.current_source`` para filtrar dados por
source (cli / ide / all). Tabs usam :func:`collect_for_tab` em vez
de chamar :func:`kiro_dash.parser.load_all_sessions` direto.
"""
from __future__ import annotations

from kiro_dash.models import Session


def get_current_source(widget) -> str:
    """Retorna ``self.app.current_source`` ou ``"all"`` por default.

    Defensivo: se o widget não está mounted ou o app não tem o
    atributo (versões antigas), cai para ``"all"``.
    """
    return getattr(getattr(widget, "app", None), "current_source", "all")


def collect_for_tab(widget) -> list[Session]:
    """Coleta sessões respeitando ``self.app.current_source``.

    Lazy import para evitar ciclo com ``sources``.
    """
    from kiro_dash.sources import collect_sessions

    source = get_current_source(widget)
    return collect_sessions(source)
