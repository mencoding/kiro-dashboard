"""Testes dos subcomandos audit."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from click.testing import CliRunner

from kiro_dash.cli import main
from kiro_dash.models import LockInfo
from tests.fixtures.sessions_synthetic import make_session, make_turn


def _running_session():
    return make_session(
        session_id="abcdef12",
        is_active=True,
        turns=[make_turn(end_timestamp=None)],
    )


def test_audit_running_lists_sessions():
    s = _running_session()
    with patch("kiro_dash.cli.load_all_sessions", return_value=[s]), \
         patch("kiro_dash.cli.read_lock",
               return_value=LockInfo(pid=999, started_at=datetime.now(timezone.utc))):
        runner = CliRunner()
        result = runner.invoke(main, ["audit", "running"])
    assert result.exit_code == 0
    assert "abcdef12" in result.output


def test_audit_running_empty_message():
    with patch("kiro_dash.cli.load_all_sessions", return_value=[]):
        runner = CliRunner()
        result = runner.invoke(main, ["audit", "running"])
    assert result.exit_code == 0
    assert "nenhuma" in result.output.lower()


def test_audit_stuck_respects_threshold():
    s = _running_session()
    started = datetime.now(timezone.utc) - timedelta(minutes=15)
    with patch("kiro_dash.cli.load_all_sessions", return_value=[s]), \
         patch("kiro_dash.watchdog.read_lock",
               return_value=LockInfo(pid=999, started_at=started)):
        runner = CliRunner()
        result = runner.invoke(main, ["audit", "stuck", "--threshold", "600"])
    assert result.exit_code == 0
    assert "abcdef12" in result.output
