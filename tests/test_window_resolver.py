"""Cobertura do resolver de janela nomeada (--window)."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from kiro_dash.aggregator import resolve_window
from tests.fixtures.sessions_synthetic import make_session, make_turn


def _turn(when: datetime, credits: float = 1.0):
    return make_turn(end_timestamp=when, credits=credits)


def test_resolve_window_today():
    now = datetime.now().astimezone()
    today = make_session(turns=[_turn(now.astimezone(timezone.utc))])
    yesterday = make_session(
        session_id="y",
        turns=[_turn((now - timedelta(days=1)).astimezone(timezone.utc))],
    )
    pairs = resolve_window([today, yesterday], "today", cycle_start=date.today().replace(day=1))
    assert len(pairs) == 1


def test_resolve_window_week():
    now = datetime.now(timezone.utc)
    s = make_session(turns=[
        _turn(now - timedelta(days=2)),
        _turn(now - timedelta(days=10)),
    ])
    pairs = resolve_window([s], "week", cycle_start=date(2000, 1, 1))
    assert len(pairs) == 1


def test_resolve_window_month():
    now = datetime.now(timezone.utc)
    s = make_session(turns=[
        _turn(now - timedelta(days=15)),
        _turn(now - timedelta(days=45)),
    ])
    pairs = resolve_window([s], "month", cycle_start=date(2000, 1, 1))
    assert len(pairs) == 1


def test_resolve_window_cycle():
    cycle_start = date.today().replace(day=1)
    now = datetime.now(timezone.utc)
    s = make_session(turns=[
        _turn(now),
        _turn(now - timedelta(days=400)),
    ])
    pairs = resolve_window([s], "cycle", cycle_start=cycle_start)
    assert len(pairs) == 1


def test_resolve_window_all():
    now = datetime.now(timezone.utc)
    s = make_session(turns=[
        _turn(now - timedelta(days=400)),
        _turn(now),
    ])
    pairs = resolve_window([s], "all", cycle_start=date(2000, 1, 1))
    assert len(pairs) == 2


def test_resolve_window_int_string_dias():
    now = datetime.now(timezone.utc)
    s = make_session(turns=[_turn(now - timedelta(days=3))])
    pairs = resolve_window([s], "5", cycle_start=date(2000, 1, 1))
    assert len(pairs) == 1
    pairs = resolve_window([s], "2", cycle_start=date(2000, 1, 1))
    assert len(pairs) == 0


def test_resolve_window_invalid_raises():
    with pytest.raises(ValueError):
        resolve_window([], "ontem", cycle_start=date(2000, 1, 1))


def test_resolve_window_now_injetado():
    fake_now = datetime(2026, 5, 16, 15, 0, tzinfo=timezone.utc)
    s = make_session(turns=[
        _turn(fake_now - timedelta(days=2), credits=5),
        _turn(fake_now - timedelta(days=10), credits=20),
    ])
    pairs = resolve_window([s], "week", cycle_start=date(2000, 1, 1), now=fake_now)
    assert len(pairs) == 1
    assert pairs[0][1].credits == 5
