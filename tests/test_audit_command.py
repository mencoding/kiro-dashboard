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


def test_audit_kill_term_via_input():
    """Usuário digita 't' → SIGTERM."""
    s = _running_session()
    started = datetime.now(timezone.utc) - timedelta(minutes=5)
    with patch("kiro_dash.cli.load_all_sessions", return_value=[s]), \
         patch("kiro_dash.cli.read_lock",
               return_value=LockInfo(pid=999, started_at=started)), \
         patch("kiro_dash.watchdog.read_lock",
               return_value=LockInfo(pid=999, started_at=started)), \
         patch("kiro_dash.watchdog.kill_pid", return_value=(True, None)) as mock_kill:
        runner = CliRunner()
        result = runner.invoke(main, ["audit", "kill", "abcdef12"], input="t\n")
    assert result.exit_code == 0
    mock_kill.assert_called_once()
    args = mock_kill.call_args[0]
    assert args[0] == 999
    assert args[1] == 15  # signal.SIGTERM


def test_audit_kill_force_via_input():
    """Usuário digita 'k' → SIGKILL."""
    s = _running_session()
    started = datetime.now(timezone.utc) - timedelta(minutes=5)
    with patch("kiro_dash.cli.load_all_sessions", return_value=[s]), \
         patch("kiro_dash.cli.read_lock",
               return_value=LockInfo(pid=999, started_at=started)), \
         patch("kiro_dash.watchdog.read_lock",
               return_value=LockInfo(pid=999, started_at=started)), \
         patch("kiro_dash.watchdog.kill_pid", return_value=(True, None)) as mock_kill:
        runner = CliRunner()
        result = runner.invoke(main, ["audit", "kill", "abcdef12"], input="k\n")
    assert result.exit_code == 0
    mock_kill.assert_called_once()
    assert mock_kill.call_args[0][1] == 9  # signal.SIGKILL


def test_audit_kill_cancel_does_nothing():
    s = _running_session()
    with patch("kiro_dash.cli.load_all_sessions", return_value=[s]), \
         patch("kiro_dash.cli.read_lock",
               return_value=LockInfo(pid=999,
                                     started_at=datetime.now(timezone.utc))), \
         patch("kiro_dash.watchdog.kill_pid") as mock_kill:
        runner = CliRunner()
        result = runner.invoke(main, ["audit", "kill", "abcdef12"], input="c\n")
    assert result.exit_code == 0
    mock_kill.assert_not_called()
    assert "cancel" in result.output.lower()


def test_audit_kill_nonexistent_sid():
    with patch("kiro_dash.cli.load_all_sessions", return_value=[]):
        runner = CliRunner()
        result = runner.invoke(main, ["audit", "kill", "deadbeef"], input="t\n")
    assert result.exit_code != 0
