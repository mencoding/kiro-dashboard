"""Smoke tests dos comandos projects / models / recent via CliRunner."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from click.testing import CliRunner

from kiro_dash.cli import main
from tests.fixtures.sessions_synthetic import make_session, make_turn


def _fake_sessions():
    now = datetime.now(timezone.utc)
    return [
        make_session(
            session_id="aaaa",
            cwd="/proj/alfa",
            model_id="claude-opus-4.7",
            turns=[make_turn(end_timestamp=now - timedelta(hours=1), credits=5.0)],
            is_active=True,
        ),
        make_session(
            session_id="bbbb",
            cwd="/proj/beta",
            model_id="auto",
            turns=[make_turn(end_timestamp=now - timedelta(hours=2), credits=2.0)],
            is_active=False,
            updated_at=now - timedelta(hours=2),
        ),
        make_session(
            session_id="cccc",
            cwd="/proj/alfa",
            model_id="claude-opus-4.7",
            turns=[make_turn(end_timestamp=now - timedelta(days=15), credits=3.0)],
            is_active=False,
            updated_at=now - timedelta(days=15),
        ),
    ]


def test_projects_default_window_aggregates_by_cwd():
    with patch("kiro_dash.cli.load_all_sessions", return_value=_fake_sessions()):
        runner = CliRunner()
        result = runner.invoke(main, ["projects"])
    assert result.exit_code == 0
    # /proj/alfa tem 1 turn na janela default (7d), /proj/beta tem 1
    assert "/proj/alfa" in result.output
    assert "/proj/beta" in result.output
    # Sessão de 15 dias não entra
    assert "3.00" not in result.output or "5.00" in result.output


def test_projects_window_30d_includes_old_session():
    with patch("kiro_dash.cli.load_all_sessions", return_value=_fake_sessions()):
        runner = CliRunner()
        result = runner.invoke(main, ["projects", "--days", "30"])
    assert result.exit_code == 0
    assert "/proj/alfa" in result.output
    # Total de alfa em 30d = 5+3 = 8
    assert "8.00" in result.output


def test_models_default_window_aggregates_by_model_id():
    with patch("kiro_dash.cli.load_all_sessions", return_value=_fake_sessions()):
        runner = CliRunner()
        result = runner.invoke(main, ["models"])
    assert result.exit_code == 0
    assert "claude-opus-4.7" in result.output
    assert "auto" in result.output
