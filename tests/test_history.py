"""Testes do módulo kiro_dash.history — queries históricas."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from kiro_dash.history import (
    PeriodSummary,
    diff_summaries,
    live_day_as_period,
    live_window_as_period,
    month_summary,
    year_summary,
)
from kiro_dash.snapshots import SnapshotPaths


@pytest.fixture
def snap_dir(tmp_path):
    """Cria snapshots fake para 3 dias de janeiro 2026."""
    for day, credits, turns, sessions in [
        (10, 5.0, 20, 3),
        (11, 3.5, 15, 2),
        (12, 7.0, 30, 4),
    ]:
        d = date(2026, 1, day)
        snap = {
            "schema_version": 1,
            "local_date": d.isoformat(),
            "totals": {"credits": credits, "turns": turns, "sessions": sessions},
        }
        fp = tmp_path / f"{d.isoformat()}.testhost.json"
        fp.write_text(json.dumps(snap))
    return SnapshotPaths(root=tmp_path)


def test_month_summary_aggregates(snap_dir):
    s = month_summary(2026, 1, paths=snap_dir)
    assert s.credits == 15.5
    assert s.turns == 65
    assert s.sessions == 9
    assert s.label == "2026-01"


def test_month_summary_empty_month(snap_dir):
    s = month_summary(2026, 2, paths=snap_dir)
    assert s.credits == 0.0
    assert s.turns == 0


def test_year_summary(snap_dir):
    s = year_summary(2026, paths=snap_dir)
    assert s.credits == 15.5  # only jan has data
    assert s.label == "2026"


def test_diff_summaries():
    a = PeriodSummary(label="hoje", credits=10.0, turns=50, sessions=5)
    b = PeriodSummary(label="ontem", credits=8.0, turns=40, sessions=4)
    d = diff_summaries(a, b)
    assert d["credits_delta"] == 2.0
    assert d["credits_pct"] == pytest.approx(0.25)
    assert d["a_label"] == "hoje"
    assert d["b_label"] == "ontem"


def test_diff_summaries_zero_base():
    a = PeriodSummary(label="a", credits=5.0, turns=10, sessions=1)
    b = PeriodSummary(label="b", credits=0.0, turns=0, sessions=0)
    d = diff_summaries(a, b)
    assert d["credits_pct"] is None


def test_live_day_as_period(snap_dir):
    p = live_day_as_period(date(2026, 1, 11), paths=snap_dir, label="ontem")
    assert p.credits == 3.5
    assert p.label == "ontem"


def test_live_day_as_period_missing(snap_dir):
    p = live_day_as_period(date(2026, 1, 1), paths=snap_dir)
    assert p.credits == 0.0


def test_live_window_as_period(snap_dir):
    p = live_window_as_period(date(2026, 1, 10), 3, paths=snap_dir, label="3 dias")
    assert p.credits == 15.5
    assert p.turns == 65
    assert p.label == "3 dias"
