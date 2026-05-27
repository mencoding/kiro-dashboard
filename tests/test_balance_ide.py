"""Testes do comando ``kiro-dash balance`` com detecção de IDE (Wave 6)."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from kiro_dash.backends.cli_json import CliJsonBackend
from kiro_dash.backends.ide_state import IdeStateBackend
from kiro_dash.cli import main
from kiro_dash.sources import Sources
from tests.fixtures.ide.build_state_vscdb import build_state_vscdb


def _make_sources(*, with_ide: bool, with_cli: bool, tmp_path: Path) -> Sources:
    cli_dir = tmp_path / "no_cli"
    if with_cli:
        cli_dir.mkdir(parents=True)
    cli = CliJsonBackend(sessions_dir=cli_dir) if with_cli else None

    if with_ide:
        db = build_state_vscdb(tmp_path / "kiro_user")
        ide = IdeStateBackend(db_path=db)
    else:
        ide = None

    return Sources(cli_json=cli, ide_state=ide)


def test_balance_uses_ide_when_available(tmp_path):
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        f'[plan]\ntier = "pro"\nmonthly_credits = 1000\n'
        f'cycle_start = {date.today().replace(day=1).isoformat()}\n'
    )
    sources = _make_sources(with_ide=True, with_cli=True, tmp_path=tmp_path)

    with patch("kiro_dash.cli.default_config_path", return_value=cfg_path), \
         patch("kiro_dash.cli.Sources.detect", return_value=sources):
        runner = CliRunner()
        result = runner.invoke(main, ["balance"])
    assert result.exit_code == 0
    # Deve aparecer painel autoritativo com fixture (currentUsage=100, limit=1000)
    assert "autoritativo" in result.output
    assert "100" in result.output
    assert "1000" in result.output
    assert "ide (state.vscdb)" in result.output


def test_balance_no_ide_flag_forces_local(tmp_path):
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        f'[plan]\ntier = "pro"\nmonthly_credits = 1000\n'
        f'cycle_start = {date.today().replace(day=1).isoformat()}\n'
    )
    sources = _make_sources(with_ide=True, with_cli=True, tmp_path=tmp_path)

    with patch("kiro_dash.cli.default_config_path", return_value=cfg_path), \
         patch("kiro_dash.cli.Sources.detect", return_value=sources), \
         patch("kiro_dash.cli.load_all_sessions", return_value=[]):
        runner = CliRunner()
        result = runner.invoke(main, ["balance", "--no-ide"])
    assert result.exit_code == 0
    assert "estimativa" in result.output
    assert "estimativa local (cli)" in result.output


def test_balance_falls_back_when_no_ide_detected(tmp_path):
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        f'[plan]\ntier = "pro"\nmonthly_credits = 1000\n'
        f'cycle_start = {date.today().replace(day=1).isoformat()}\n'
    )
    sources = _make_sources(with_ide=False, with_cli=True, tmp_path=tmp_path)

    with patch("kiro_dash.cli.default_config_path", return_value=cfg_path), \
         patch("kiro_dash.cli.Sources.detect", return_value=sources), \
         patch("kiro_dash.cli.load_all_sessions", return_value=[]), \
         patch("kiro_dash.cli.should_show_ide_banner", return_value=False):
        runner = CliRunner()
        result = runner.invoke(main, ["balance"])
    assert result.exit_code == 0
    assert "estimativa" in result.output


def test_balance_shows_banner_when_only_cli(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        f'[plan]\ntier = "pro"\nmonthly_credits = 1000\n'
        f'cycle_start = {date.today().replace(day=1).isoformat()}\n'
    )
    sources = _make_sources(with_ide=False, with_cli=True, tmp_path=tmp_path)
    banner_state = tmp_path / "banner_state.json"

    monkeypatch.setattr(
        "kiro_dash.onboarding.banner_state_path", lambda: banner_state
    )

    with patch("kiro_dash.cli.default_config_path", return_value=cfg_path), \
         patch("kiro_dash.cli.Sources.detect", return_value=sources), \
         patch("kiro_dash.cli.load_all_sessions", return_value=[]):
        runner = CliRunner()
        result = runner.invoke(main, ["balance"])
    assert result.exit_code == 0
    assert "kiro.dev" in result.output
    assert "KIRO_DASH_NO_BANNER" in result.output
    assert banner_state.exists()


def test_plan_get_includes_ide_info_when_available(tmp_path):
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        '[plan]\ntier = "pro+"\nmonthly_credits = 2000\ncycle_start = 2026-05-01\n'
    )
    sources = _make_sources(with_ide=True, with_cli=True, tmp_path=tmp_path)

    with patch("kiro_dash.cli.default_config_path", return_value=cfg_path), \
         patch("kiro_dash.cli.Sources.detect", return_value=sources):
        runner = CliRunner()
        result = runner.invoke(main, ["plan", "get"])
    assert result.exit_code == 0
    assert "Limite servidor" in result.output
    assert "1000" in result.output  # usage_limit da fixture
    assert "Reset em" in result.output


def test_plan_get_shows_only_local_when_no_ide(tmp_path):
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        '[plan]\ntier = "pro+"\nmonthly_credits = 2000\ncycle_start = 2026-05-01\n'
    )
    sources = _make_sources(with_ide=False, with_cli=True, tmp_path=tmp_path)

    with patch("kiro_dash.cli.default_config_path", return_value=cfg_path), \
         patch("kiro_dash.cli.Sources.detect", return_value=sources):
        runner = CliRunner()
        result = runner.invoke(main, ["plan", "get"])
    assert result.exit_code == 0
    assert "pro+" in result.output
    assert "Limite servidor" not in result.output


def test_whoami_shows_sources_panel(tmp_path):
    """Smoke do whoami com Sources panel adicional."""
    sources = _make_sources(with_ide=False, with_cli=False, tmp_path=tmp_path)

    fake_info = type("X", (), {})()
    fake_info.account_type = "BuilderId"
    fake_info.email = "user@example.com"
    fake_info.region = "us-east-1"
    fake_info.start_url = None
    fake_info.profile_name = "test"
    fake_info.profile_arn = None
    fake_info.aws_account_id = None
    fake_info.profile_region = None
    fake_info.is_enterprise = False

    with patch("kiro_dash.cli.run_whoami", return_value=fake_info), \
         patch("kiro_dash.cli.Sources.detect", return_value=sources):
        runner = CliRunner()
        result = runner.invoke(main, ["whoami"])
    assert result.exit_code == 0
    assert "Identidade Kiro CLI" in result.output
    assert "Fontes detectadas" in result.output
