"""Smoke tests para comandos CLI de histórico (today --day, month, year, compare)."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from kiro_dash.cli import main
from kiro_dash.snapshots import SnapshotPaths


def _write_snap(tmp_path: Path, d: date, *, credits: float = 10, turns: int = 3, sessions: int = 1):
    snap_dir = tmp_path / "kiro-dash" / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "local_date": d.isoformat(),
        "tz_offset": "-03:00",
        "captured_at": "2026-05-17T03:00:00Z",
        "captured_by_host": "test",
        "totals": {"credits": credits, "turns": turns, "sessions": sessions},
        "by_model": [{"label": "claude-opus-4", "credits": credits,
                      "turns": turns, "sessions": sessions,
                      "duration_secs": 120, "tool_uses": 5}],
        "by_project": [{"label": "kiro-dash", "credits": credits,
                        "turns": turns, "sessions": sessions,
                        "duration_secs": 120, "tool_uses": 5}],
        "by_agent_pair": [], "by_session": [], "by_tool": [],
    }
    with open(snap_dir / f"{d.isoformat()}.test.json", "w") as f:
        json.dump(payload, f)


def test_today_day_old_reads_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    old_date = date.today() - timedelta(days=5)
    _write_snap(tmp_path, old_date, credits=42.5, turns=7)

    runner = CliRunner()
    with patch("kiro_dash.cli._ensure_snapshots_silently"):
        result = runner.invoke(main, ["today", "--day", old_date.isoformat()])
    assert result.exit_code == 0
    assert "42.50" in result.output
    assert "snapshot" in result.output.lower()


def test_today_day_old_no_snapshot_warns(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    old_date = date.today() - timedelta(days=10)

    runner = CliRunner()
    with patch("kiro_dash.cli._ensure_snapshots_silently"):
        result = runner.invoke(main, ["today", "--day", old_date.isoformat()])
    assert result.exit_code == 0
    assert "sem snapshot" in result.output.lower()


def test_month_command_sem_snapshots_avisa(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(main, ["month", "2026-01"])
    assert result.exit_code == 0
    assert "sem snapshots" in result.output.lower()


def test_month_command_com_dados(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    _write_snap(tmp_path, date(2026, 3, 1), credits=10, turns=2)
    _write_snap(tmp_path, date(2026, 3, 15), credits=20, turns=4)

    runner = CliRunner()
    result = runner.invoke(main, ["month", "2026-03"])
    assert result.exit_code == 0
    assert "30.00" in result.output
    assert "2026-03" in result.output


def test_year_command_aceita_sem_arg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(main, ["year"])
    assert result.exit_code == 0


def test_year_command_com_dados(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    _write_snap(tmp_path, date(2026, 1, 5), credits=15, turns=3)
    _write_snap(tmp_path, date(2026, 6, 10), credits=25, turns=5)

    runner = CliRunner()
    result = runner.invoke(main, ["year", "2026"])
    assert result.exit_code == 0
    assert "40.00" in result.output
    assert "2026" in result.output


def test_compare_month_vs_month(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    _write_snap(tmp_path, date(2026, 4, 1), credits=80, turns=15, sessions=8)
    _write_snap(tmp_path, date(2026, 5, 1), credits=100, turns=20, sessions=10)

    runner = CliRunner()
    result = runner.invoke(main, ["compare", "2026-05", "2026-04"])
    assert result.exit_code == 0
    assert "2026-05" in result.output
    assert "2026-04" in result.output


def test_compare_today_yesterday(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    runner = CliRunner()
    with patch("kiro_dash.cli.load_all_sessions", return_value=[]):
        result = runner.invoke(main, ["compare", "today", "yesterday"])
    assert result.exit_code == 0
    assert "hoje" in result.output.lower()
    assert "ontem" in result.output.lower()


def test_compare_invalid_period_falha(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(main, ["compare", "xyz", "2026"])
    assert result.exit_code != 0
