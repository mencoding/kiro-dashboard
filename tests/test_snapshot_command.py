"""Smoke do subcomando snapshot."""
from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from kiro_dash.cli import main


def test_snapshot_sem_args_gera_lazy(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    with patch("kiro_dash.cli.load_all_sessions", return_value=[]):
        runner = CliRunner()
        result = runner.invoke(main, ["snapshot"])
    assert result.exit_code == 0


def test_snapshot_com_data_gera_dia_especifico(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    with patch("kiro_dash.cli.load_all_sessions", return_value=[]):
        runner = CliRunner()
        result = runner.invoke(main, ["snapshot", "2026-05-16"])
    assert result.exit_code == 0


def test_snapshot_data_invalida_falha(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(main, ["snapshot", "2026/05/16"])
    assert result.exit_code != 0
