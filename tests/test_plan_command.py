"""Smoke dos subcomandos plan, balance e aliases."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

from click.testing import CliRunner

from kiro_dash.cli import main
from kiro_dash.config import load_aliases, save_aliases
from tests.fixtures.sessions_synthetic import make_session, make_turn


def test_plan_get_shows_current_plan(tmp_path):
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text('[plan]\ntier = "pro+"\nmonthly_credits = 2000\ncycle_start = 2026-05-01\n')
    with patch("kiro_dash.cli.default_config_path", return_value=cfg_path):
        runner = CliRunner()
        result = runner.invoke(main, ["plan", "get"])
    assert result.exit_code == 0
    assert "pro+" in result.output
    assert "2000" in result.output
    assert "2026-05-01" in result.output


def test_plan_set_persists_tier(tmp_path):
    cfg_path = tmp_path / "config.toml"
    with patch("kiro_dash.cli.default_config_path", return_value=cfg_path):
        runner = CliRunner()
        result = runner.invoke(main, ["plan", "set", "pro+"])
    assert result.exit_code == 0
    content = cfg_path.read_text()
    assert 'tier = "pro+"' in content
    assert 'monthly_credits = 2000' in content


def test_plan_set_invalid_tier_rejects(tmp_path):
    cfg_path = tmp_path / "config.toml"
    with patch("kiro_dash.cli.default_config_path", return_value=cfg_path):
        runner = CliRunner()
        result = runner.invoke(main, ["plan", "set", "wrong-tier"])
    assert result.exit_code != 0


def test_plan_set_with_credits_override(tmp_path):
    cfg_path = tmp_path / "config.toml"
    with patch("kiro_dash.cli.default_config_path", return_value=cfg_path):
        runner = CliRunner()
        result = runner.invoke(main, [
            "plan", "set", "pro", "--credits", "1500", "--cycle-start", "2026-04-15"
        ])
    assert result.exit_code == 0
    content = cfg_path.read_text()
    assert 'monthly_credits = 1500' in content
    assert '2026-04-15' in content


def _fake_sessions_with_credits(total_credits: float):
    now = datetime.now(timezone.utc)
    return [make_session(turns=[
        make_turn(end_timestamp=now - timedelta(hours=1), credits=total_credits),
    ])]


def test_balance_shows_consumption_below_threshold(tmp_path):
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        f'[plan]\ntier = "pro+"\nmonthly_credits = 2000\n'
        f'cycle_start = {date.today().replace(day=1).isoformat()}\n'
    )
    with patch("kiro_dash.cli.default_config_path", return_value=cfg_path), \
         patch("kiro_dash.cli.load_all_sessions", return_value=_fake_sessions_with_credits(500.0)):
        runner = CliRunner()
        result = runner.invoke(main, ["balance"])
    assert result.exit_code == 0
    assert "500" in result.output
    assert "1500" in result.output
    assert "25" in result.output


def test_balance_warns_when_above_80_pct(tmp_path):
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        f'[plan]\ntier = "pro"\nmonthly_credits = 1000\n'
        f'cycle_start = {date.today().replace(day=1).isoformat()}\n'
    )
    with patch("kiro_dash.cli.default_config_path", return_value=cfg_path), \
         patch("kiro_dash.cli.load_all_sessions", return_value=_fake_sessions_with_credits(850.0)):
        runner = CliRunner()
        result = runner.invoke(main, ["balance"])
    assert result.exit_code == 0
    assert "85" in result.output


def test_aliases_get_lista_existentes(tmp_path):
    cfg = tmp_path / "config.toml"
    save_aliases({"/x": "alpha", "/y": "beta"}, cfg)
    with patch("kiro_dash.cli.default_config_path", return_value=cfg):
        runner = CliRunner()
        result = runner.invoke(main, ["aliases", "get"])
    assert result.exit_code == 0
    assert "alpha" in result.output
    assert "beta" in result.output


def test_aliases_set_persiste(tmp_path):
    cfg = tmp_path / "config.toml"
    with patch("kiro_dash.cli.default_config_path", return_value=cfg):
        runner = CliRunner()
        result = runner.invoke(main, ["aliases", "set", "/srv/foo", "foo-projeto"])
    assert result.exit_code == 0
    assert load_aliases(cfg) == {"/srv/foo": "foo-projeto"}


def test_aliases_unset_remove(tmp_path):
    cfg = tmp_path / "config.toml"
    save_aliases({"/x": "alpha", "/y": "beta"}, cfg)
    with patch("kiro_dash.cli.default_config_path", return_value=cfg):
        runner = CliRunner()
        result = runner.invoke(main, ["aliases", "unset", "/x"])
    assert result.exit_code == 0
    assert load_aliases(cfg) == {"/y": "beta"}
