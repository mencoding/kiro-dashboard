"""Testes dos widgets de aba — funções puras de snapshot."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from kiro_dash.views.tabs.now_tab import build_now_snapshot
from tests.fixtures.sessions_synthetic import make_session, make_turn


def _two_sessions():
    now = datetime.now(timezone.utc)
    return [
        make_session(
            session_id="aaaa",
            is_active=True,
            turns=[make_turn(end_timestamp=now - timedelta(minutes=2), credits=3.0)],
        ),
        make_session(
            session_id="bbbb",
            is_active=False,
            turns=[make_turn(end_timestamp=now - timedelta(hours=2), credits=1.0)],
        ),
    ]


def test_build_now_snapshot_only_active():
    snap = build_now_snapshot(_two_sessions())
    assert snap.active_count == 1
    assert snap.today_credits >= 0
    assert any("aaaa" in row[0] for row in snap.rows)
    assert all("bbbb" not in row[0] for row in snap.rows)


def test_build_now_snapshot_empty_when_no_active():
    snap = build_now_snapshot([make_session(session_id="x", is_active=False)])
    assert snap.active_count == 0
    assert snap.rows == []

from kiro_dash.views.tabs.today_tab import build_today_snapshot


def test_build_today_snapshot_aggregates():
    sessions = _two_sessions()
    snap = build_today_snapshot(sessions)
    assert len(snap.by_model) >= 1
    assert snap.total_credits >= 0

from kiro_dash.views.tabs.models_tab import build_models_snapshot
from kiro_dash.views.tabs.projects_tab import build_projects_snapshot


def test_build_projects_snapshot_uses_window():
    sessions = _two_sessions()
    snap = build_projects_snapshot(sessions, days=7)
    assert snap.window_days == 7
    if len(snap.aggs) >= 2:
        assert snap.aggs[0].credits >= snap.aggs[1].credits


def test_build_models_snapshot_uses_window():
    sessions = _two_sessions()
    snap = build_models_snapshot(sessions, days=30)
    assert snap.window_days == 30

from kiro_dash.views.tabs.session_tab import SessionTab  # noqa: F401


def test_session_tab_module_imports_cleanly():
    """Smoke — o módulo importa sem erro."""
    from kiro_dash.views.tabs import session_tab
    assert hasattr(session_tab, "SessionTab")
