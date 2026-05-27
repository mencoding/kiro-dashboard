"""Cobertura do watchdog (detector + kill)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from kiro_dash.models import LockInfo
from kiro_dash.watchdog import (
    is_session_running,
    running_sessions,
    stuck_sessions,
)
from tests.fixtures.sessions_synthetic import make_session, make_turn


def _now():
    return datetime.now(timezone.utc)


def test_is_session_running_when_last_turn_in_progress():
    s = make_session(
        is_active=True,
        turns=[make_turn(end_timestamp=None)],
    )
    assert is_session_running(s) is True


def test_is_session_not_running_when_lock_but_turns_finished():
    s = make_session(
        is_active=True,
        turns=[make_turn(end_timestamp=_now())],
    )
    assert is_session_running(s) is False


def test_is_session_not_running_when_no_lock():
    s = make_session(
        is_active=False,
        turns=[make_turn(end_timestamp=None)],
    )
    assert is_session_running(s) is False


def test_running_sessions_filters_correctly():
    s_running = make_session(
        session_id="r",
        is_active=True,
        turns=[make_turn(end_timestamp=None)],
    )
    s_idle = make_session(
        session_id="i",
        is_active=True,
        turns=[make_turn(end_timestamp=_now())],
    )
    s_offline = make_session(session_id="o", is_active=False, turns=[])
    out = running_sessions([s_running, s_idle, s_offline])
    assert [s.session_id for s in out] == ["r"]


def test_stuck_sessions_uses_lock_started_at():
    s = make_session(
        session_id="stuck",
        is_active=True,
        turns=[make_turn(end_timestamp=None)],
    )
    s_fresh = make_session(
        session_id="fresh",
        is_active=True,
        turns=[make_turn(end_timestamp=None)],
    )

    def fake_read_lock(sid, sessions_dir=None):
        if sid == "stuck":
            return LockInfo(pid=111, started_at=_now() - timedelta(minutes=30))
        if sid == "fresh":
            return LockInfo(pid=222, started_at=_now() - timedelta(seconds=10))
        return None

    with patch("kiro_dash.watchdog.read_lock", side_effect=fake_read_lock):
        out = stuck_sessions([s, s_fresh], threshold_secs=600)
    assert [s.session_id for s, _ in out] == ["stuck"]
