"""Testes da função de saldo de ciclo."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from kiro_dash.aggregator import balance_in_cycle, turns_in_cycle
from tests.fixtures.sessions_synthetic import make_session, make_turn


def test_turns_in_cycle_includes_only_after_cycle_start():
    cycle_start = date(2026, 5, 1)
    # O pivô é cycle_start 00:00 local → converte pra UTC.
    # Usamos timestamps que estejam claramente antes/depois.
    s = make_session(turns=[
        make_turn(end_timestamp=datetime(2026, 4, 29, 12, 0, tzinfo=timezone.utc), credits=1.0),
        make_turn(end_timestamp=datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc), credits=2.0),
        make_turn(end_timestamp=datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc), credits=3.0),
    ])
    pairs = turns_in_cycle([s], cycle_start)
    creds = sorted(t.credits for _, t in pairs)
    assert creds == [2.0, 3.0]


def test_balance_in_cycle_calculates_consumed_and_remaining():
    cycle_start = date.today().replace(day=1)
    now = datetime.now(timezone.utc)
    s = make_session(turns=[
        make_turn(end_timestamp=now - timedelta(days=1), credits=300.0),
        make_turn(end_timestamp=now, credits=200.0),
    ])
    bal = balance_in_cycle([s], cycle_start, monthly_credits=1000)
    assert bal["consumed"] == 500.0
    assert bal["remaining"] == 500.0
    assert bal["pct_used"] == 50.0
    assert bal["monthly_credits"] == 1000
    assert bal["cycle_start"] == cycle_start


def test_balance_in_cycle_caps_pct_at_100_when_overage():
    cycle_start = date.today().replace(day=1)
    s = make_session(turns=[make_turn(
        end_timestamp=datetime.now(timezone.utc), credits=1500.0,
    )])
    bal = balance_in_cycle([s], cycle_start, monthly_credits=1000)
    assert bal["consumed"] == 1500.0
    assert bal["remaining"] == -500.0
    assert bal["pct_used"] == 150.0
