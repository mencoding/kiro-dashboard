"""Tests T4-W8 — Sources.summary_rows() para whoami tabela rich."""
from __future__ import annotations

from unittest.mock import MagicMock

from kiro_dash.sources import Sources


def test_summary_rows_returns_4_tuples():
    s = Sources(cli_json=None, ide_state=None, ide_sessions=None, cli_sqlite=None)
    rows = s.summary_rows()
    assert len(rows) == 4
    for row in rows:
        assert isinstance(row, tuple)
        assert len(row) == 4
        slug, symbol, color, detail = row
        assert isinstance(slug, str)
        assert symbol in ("✓", "—")
        assert isinstance(color, str)
        assert isinstance(detail, str)


def test_summary_rows_all_unavailable_uses_dash():
    s = Sources(cli_json=None, ide_state=None, ide_sessions=None)
    rows = s.summary_rows()
    for slug, symbol, color, detail in rows:
        assert symbol == "—"
        assert color == "dim"


def test_summary_rows_cli_present_uses_green_check():
    cli = MagicMock()
    cli.is_available.return_value = True
    cli.data_age.return_value = None
    s = Sources(cli_json=cli, ide_state=None, ide_sessions=None)
    rows = dict((r[0], r) for r in s.summary_rows())
    assert rows["cli"][1] == "✓"
    assert rows["cli"][2] == "green"


def test_summary_rows_ide_state_with_age_uses_freshness_color():
    backend = MagicMock()
    backend.is_available.return_value = True
    backend.data_age.return_value = 60.0  # < 3h = green
    s = Sources(cli_json=None, ide_state=backend, ide_sessions=None)
    rows = dict((r[0], r) for r in s.summary_rows())
    assert rows["ide-state"][1] == "✓"
    assert rows["ide-state"][2] == "green"
    assert "snapshot" in rows["ide-state"][3]


def test_summary_rows_ide_state_yellow_freshness():
    backend = MagicMock()
    backend.data_age.return_value = 4 * 3600.0  # 4h = yellow
    s = Sources(cli_json=None, ide_state=backend, ide_sessions=None)
    rows = dict((r[0], r) for r in s.summary_rows())
    assert rows["ide-state"][2] == "yellow"


def test_summary_rows_ide_sessions_with_workspaces():
    backend = MagicMock()
    backend.list_workspaces.return_value = [MagicMock(), MagicMock(), MagicMock()]
    backend.data_age.return_value = 60.0
    s = Sources(cli_json=None, ide_state=None, ide_sessions=backend)
    rows = dict((r[0], r) for r in s.summary_rows())
    assert rows["ide-sessions"][1] == "✓"
    assert "3 workspaces" in rows["ide-sessions"][3]


def test_summary_rows_ide_sessions_singular_one_workspace():
    backend = MagicMock()
    backend.list_workspaces.return_value = [MagicMock()]
    backend.data_age.return_value = 60.0
    s = Sources(cli_json=None, ide_state=None, ide_sessions=backend)
    rows = dict((r[0], r) for r in s.summary_rows())
    assert "1 workspace" in rows["ide-sessions"][3]
    assert "1 workspaces" not in rows["ide-sessions"][3]


def test_summary_rows_cli_sqlite_always_dash():
    """cli-sqlite é placeholder Wave 7+ — sempre dash."""
    s = Sources(cli_json=MagicMock(), ide_state=None, ide_sessions=None)
    rows = dict((r[0], r) for r in s.summary_rows())
    assert rows["cli-sqlite"][1] == "—"


def test_summary_rows_order_matches_summary_lines():
    """Rows e lines têm os mesmos slugs na mesma ordem."""
    s = Sources(cli_json=None, ide_state=None, ide_sessions=None)
    rows_slugs = [r[0] for r in s.summary_rows()]
    expected = ["cli", "ide-state", "ide-sessions", "cli-sqlite"]
    assert rows_slugs == expected
