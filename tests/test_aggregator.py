"""Testes do agregador — funções de janela temporal."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from kiro_dash.aggregator import turns_in_last_days
from tests.fixtures.sessions_synthetic import make_session, make_turn


def test_turns_in_last_days_filters_by_window():
    now = datetime.now(timezone.utc)
    s = make_session(
        turns=[
            make_turn(end_timestamp=now - timedelta(days=10), credits=1.0),
            make_turn(end_timestamp=now - timedelta(days=3), credits=2.0),
            make_turn(end_timestamp=now - timedelta(hours=1), credits=4.0),
        ]
    )

    pairs = turns_in_last_days([s], days=7)
    credits = sorted(t.credits for _, t in pairs)
    assert credits == [2.0, 4.0]


def test_turns_in_last_days_empty_when_no_match():
    now = datetime.now(timezone.utc)
    s = make_session(turns=[make_turn(end_timestamp=now - timedelta(days=30))])
    assert turns_in_last_days([s], days=7) == []


def test_turns_in_last_days_zero_days_returns_empty():
    now = datetime.now(timezone.utc)
    s = make_session(turns=[make_turn(end_timestamp=now)])
    assert turns_in_last_days([s], days=0) == []
