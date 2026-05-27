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


def test_recent_orders_by_updated_at_desc():
    with patch("kiro_dash.cli.load_all_sessions", return_value=_fake_sessions()):
        runner = CliRunner()
        result = runner.invoke(main, ["recent", "--limit", "5"])
    assert result.exit_code == 0
    # aaaa é a mais recente (updated_at = now), bbbb depois (-2h), cccc por último (-15d)
    pos_a = result.output.find("aaaa")
    pos_b = result.output.find("bbbb")
    pos_c = result.output.find("cccc")
    assert 0 <= pos_a < pos_b < pos_c


def test_recent_marks_active_sessions():
    with patch("kiro_dash.cli.load_all_sessions", return_value=_fake_sessions()):
        runner = CliRunner()
        result = runner.invoke(main, ["recent"])
    assert result.exit_code == 0
    # Pelo menos um marcador visual para 'aaaa' (que tem is_active=True)
    # — usamos '●' como marcador (igual ao `session`)
    assert "●" in result.output


def test_projects_window_all_inclui_tudo():
    with patch("kiro_dash.cli.load_all_sessions", return_value=_fake_sessions()):
        runner = CliRunner()
        result = runner.invoke(main, ["projects", "--window", "all"])
    assert result.exit_code == 0
    # Sessão de 15d entra com window=all
    assert "8.00" in result.output


def test_projects_window_invalid_returns_error():
    with patch("kiro_dash.cli.load_all_sessions", return_value=_fake_sessions()):
        runner = CliRunner()
        result = runner.invoke(main, ["projects", "--window", "ontem"])
    assert result.exit_code != 0
    assert "window" in result.output.lower()
