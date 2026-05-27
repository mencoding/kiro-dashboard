"""Tests T3-W7 — tools cmd cobre IDE."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from kiro_dash.aggregator import (
    aggregate_tools_in_window_combined,
    aggregate_tools_in_window_ide,
)
from kiro_dash.backends.ide_sessions import IdeSessionBackend
from kiro_dash.sources import Sources
from tests.fixtures.ide.build_ide_layout import (
    T_BASE,
    build_ide_layout,
)


def _ide_sources(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    return Sources(
        cli_json=None,
        ide_state=None,
        ide_sessions=IdeSessionBackend(root=kiro_root),
    )


def test_aggregate_tools_ide_in_window_returns_combined_tools(tmp_path):
    """Janela ampla cobre todas as executions da fixture."""
    sources = _ide_sources(tmp_path)
    # T_BASE = 1779912000000 ms; janela cobrindo até now é gigante
    now_dt = datetime.fromtimestamp(T_BASE / 1000.0, tz=timezone.utc) + timedelta(hours=1)
    aggs = aggregate_tools_in_window_ide(hours=24, sources=sources, now=now_dt)
    names = {a["name"] for a in aggs}
    assert {"execute_bash", "read_files", "fs_write", "str_replace"} <= names


def test_aggregate_tools_ide_window_excludes_old(tmp_path):
    """Janela curta exclui executions antigas."""
    sources = _ide_sources(tmp_path)
    # 100 anos no futuro — nada cabe na janela
    now_dt = datetime(2126, 1, 1, tzinfo=timezone.utc)
    aggs = aggregate_tools_in_window_ide(hours=1, sources=sources, now=now_dt)
    assert aggs == []


def test_aggregate_tools_ide_no_backend_returns_empty(tmp_path):
    sources = Sources(cli_json=None, ide_state=None, ide_sessions=None)
    aggs = aggregate_tools_in_window_ide(hours=24, sources=sources)
    assert aggs == []


def test_aggregate_tools_combined_dedupes_by_name(tmp_path):
    """Combined dedupe — se CLI e IDE ambos têm mesma tool, soma counts."""
    sources = _ide_sources(tmp_path)
    now_dt = datetime.fromtimestamp(T_BASE / 1000.0, tz=timezone.utc) + timedelta(hours=1)
    aggs = aggregate_tools_in_window_combined(
        sessions_dir=tmp_path / "no_cli",  # CLI vazio
        hours=24,
        sources=sources,
        now=now_dt,
    )
    # Mesmas tools de IDE só
    names = [a["name"] for a in aggs]
    assert "execute_bash" in names
    # Sorted desc by count
    counts = [a["count"] for a in aggs]
    assert counts == sorted(counts, reverse=True)


def test_aggregate_tools_combined_empty_when_neither_has_data(tmp_path):
    """Sem CLI nem IDE: lista vazia."""
    sources = Sources(cli_json=None, ide_state=None, ide_sessions=None)
    aggs = aggregate_tools_in_window_combined(
        sessions_dir=tmp_path / "no_cli",
        hours=24,
        sources=sources,
    )
    assert aggs == []
