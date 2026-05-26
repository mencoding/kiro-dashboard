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


from kiro_dash.aggregator import aggregate_tools_in_window


def test_aggregate_tools_in_window_groups_by_name(tmp_path):
    s1 = tmp_path / "11111111.jsonl"
    s2 = tmp_path / "22222222.jsonl"
    s1.write_text(
        '{"version":"v1","kind":"AssistantMessage","data":{"content":['
        '{"kind":"toolUse","data":{"name":"read","toolUseId":"a"}},'
        '{"kind":"toolUse","data":{"name":"shell","toolUseId":"b"}}'
        ']}}\n'
    )
    s2.write_text(
        '{"version":"v1","kind":"AssistantMessage","data":{"content":['
        '{"kind":"toolUse","data":{"name":"read","toolUseId":"c"}}'
        ']}}\n'
    )

    aggs = aggregate_tools_in_window(tmp_path, hours=24)
    by_name = {a["name"]: a for a in aggs}
    assert by_name["read"]["count"] == 2
    assert by_name["shell"]["count"] == 1
    assert by_name["read"]["sessions"] == 2
    assert by_name["shell"]["sessions"] == 1


def test_aggregate_tools_in_window_excludes_old_files(tmp_path):
    import os
    import time

    old = tmp_path / "old.jsonl"
    old.write_text(
        '{"version":"v1","kind":"AssistantMessage","data":{"content":['
        '{"kind":"toolUse","data":{"name":"read","toolUseId":"x"}}]}}\n'
    )
    past = time.time() - 48 * 3600
    os.utime(old, (past, past))

    aggs = aggregate_tools_in_window(tmp_path, hours=24)
    assert aggs == []
