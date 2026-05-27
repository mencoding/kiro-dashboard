"""Reconstrução de resumos por período (mês, ano) a partir de snapshots."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from kiro_dash.history import (
    PeriodSummary,
    diff_summaries,
    month_summary,
    year_summary,
)
from kiro_dash.snapshots import SnapshotPaths


def _write_fake_snapshot(paths: SnapshotPaths, d: date, host: str, *,
                         credits: float, turns: int, sessions: int):
    paths.root.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "local_date": d.isoformat(),
        "tz_offset": "-03:00",
        "captured_at": "2026-05-17T03:00:00Z",
        "captured_by_host": host,
        "totals": {"credits": credits, "turns": turns, "sessions": sessions},
        "by_model": [{"label": "claude-opus-4.7", "credits": credits,
                      "turns": turns, "sessions": sessions,
                      "duration_secs": 0, "tool_uses": 0}],
        "by_project": [], "by_agent_pair": [], "by_session": [], "by_tool": [],
    }
    with open(paths.for_date(d, host), "w") as f:
        json.dump(payload, f)


def test_month_summary_soma_dias_existentes(tmp_path):
    paths = SnapshotPaths(root=tmp_path)
    _write_fake_snapshot(paths, date(2026, 5, 1), "h1", credits=10, turns=2, sessions=1)
    _write_fake_snapshot(paths, date(2026, 5, 2), "h1", credits=20, turns=4, sessions=2)
    _write_fake_snapshot(paths, date(2026, 5, 15), "h1", credits=5, turns=1, sessions=1)

    summary = month_summary(2026, 5, paths=paths)
    assert summary.credits == 35
    assert summary.turns == 7
    assert summary.days_with_data == 3
    assert summary.period_label == "2026-05"


def test_month_summary_dias_sem_dados_n_quebram(tmp_path):
    paths = SnapshotPaths(root=tmp_path)
    summary = month_summary(2026, 5, paths=paths)
    assert summary.credits == 0
    assert summary.days_with_data == 0


def test_year_summary_agrega_meses(tmp_path):
    paths = SnapshotPaths(root=tmp_path)
    _write_fake_snapshot(paths, date(2026, 1, 1), "h1", credits=10, turns=1, sessions=1)
    _write_fake_snapshot(paths, date(2026, 6, 15), "h1", credits=20, turns=2, sessions=1)
    _write_fake_snapshot(paths, date(2026, 12, 31), "h1", credits=30, turns=3, sessions=1)

    summary = year_summary(2026, paths=paths)
    assert summary.credits == 60
    assert summary.turns == 6
    assert summary.days_with_data == 3
    assert summary.period_label == "2026"


def test_diff_summaries():
    a = PeriodSummary(period_label="2026-05", credits=100, turns=20,
                      sessions=10, days_with_data=15)
    b = PeriodSummary(period_label="2026-04", credits=80, turns=15,
                      sessions=8, days_with_data=12)
    diff = diff_summaries(a, b)
    assert diff["credits_delta"] == 20
    assert diff["credits_pct"] == pytest.approx(0.25)
    assert diff["turns_delta"] == 5


def test_diff_summaries_zero_base():
    a = PeriodSummary(period_label="2026-05", credits=50, turns=10,
                      sessions=5, days_with_data=3)
    b = PeriodSummary(period_label="2026-04", credits=0, turns=0,
                      sessions=0, days_with_data=0)
    diff = diff_summaries(a, b)
    assert diff["credits_delta"] == 50
    assert diff["credits_pct"] is None


def test_month_summary_agrega_by_model(tmp_path):
    paths = SnapshotPaths(root=tmp_path)
    _write_fake_snapshot(paths, date(2026, 5, 1), "h1", credits=10, turns=2, sessions=1)
    _write_fake_snapshot(paths, date(2026, 5, 2), "h1", credits=20, turns=4, sessions=2)

    summary = month_summary(2026, 5, paths=paths)
    assert len(summary.by_model) == 1
    assert summary.by_model[0]["label"] == "claude-opus-4.7"
    assert summary.by_model[0]["credits"] == 30
