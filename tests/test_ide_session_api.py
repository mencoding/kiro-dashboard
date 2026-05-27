"""Tests T8+T9 — API completa IdeSessionBackend (list/iter/running)."""
from __future__ import annotations

import time

from kiro_dash.backends.ide_mapper import composite_session_id
from kiro_dash.backends.ide_sessions import IdeSessionBackend
from kiro_dash.jsonl_parser import ToolCall
from kiro_dash.models import Session, Turn
from tests.fixtures.ide.build_ide_layout import (
    DEFAULT_WORKSPACE_PATH,
    EXEC_CHAT,
    EXEC_DO_COMPLEX,
    SESSION_ID,
    build_ide_layout,
)


# ── T8: list_sessions ────────────────────────────────────────────────


def test_list_sessions_returns_typed_session(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    backend = IdeSessionBackend(root=kiro_root)
    sessions = backend.list_sessions()
    assert len(sessions) == 1
    s = sessions[0]
    assert isinstance(s, Session)
    assert s.session_id == composite_session_id(SESSION_ID)
    assert s.cwd == DEFAULT_WORKSPACE_PATH
    assert s.agent_name == "kiro-ide"
    assert s.model_id == "kiro:auto"
    assert len(s.turns) == 7  # 7 executions


def test_list_sessions_empty_when_unavailable(tmp_path):
    backend = IdeSessionBackend(root=tmp_path / "nope")
    assert backend.list_sessions() == []


def test_list_sessions_with_multiple_workspaces(tmp_path):
    extra = ["/home/test/another", "/srv/lab/xyz"]
    kiro_root = build_ide_layout(tmp_path, extra_workspaces=extra)
    backend = IdeSessionBackend(root=kiro_root)
    sessions = backend.list_sessions()
    # Cada workspace tem 1 sessão com mesmo SESSION_ID — esperado: 3 entries
    # com cwds diferentes
    assert len(sessions) == 3
    cwds = {s.cwd for s in sessions}
    assert cwds == {DEFAULT_WORKSPACE_PATH, *extra}


def test_list_sessions_aggregates_credits_from_all_executions(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    backend = IdeSessionBackend(root=kiro_root)
    sessions = backend.list_sessions()
    s = sessions[0]
    # Soma esperada: chat (~0.094) + do_simple (~0.146) + do_complex (~0.66)
    # + do_write (~0.499) + spec_dispatch (~0.008) + spec_gen (~0.55) +
    # running (~0.12) → ~2.08+
    assert s.total_credits > 1.5
    assert s.total_credits < 5.0


def test_list_sessions_session_is_active_when_running_exists(tmp_path):
    kiro_root = build_ide_layout(tmp_path, include_running=True)
    backend = IdeSessionBackend(root=kiro_root)
    sessions = backend.list_sessions()
    assert sessions[0].is_active is True


def test_list_sessions_session_inactive_when_no_running(tmp_path):
    kiro_root = build_ide_layout(tmp_path, include_running=False)
    backend = IdeSessionBackend(root=kiro_root)
    sessions = backend.list_sessions()
    assert sessions[0].is_active is False


# ── T8: iter_turns ───────────────────────────────────────────────────


def test_iter_turns_with_raw_session_id(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    backend = IdeSessionBackend(root=kiro_root)
    turns = list(backend.iter_turns(SESSION_ID))
    assert len(turns) == 7
    assert all(isinstance(t, Turn) for t in turns)


def test_iter_turns_with_composite_session_id(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    backend = IdeSessionBackend(root=kiro_root)
    composite = composite_session_id(SESSION_ID)
    turns = list(backend.iter_turns(composite))
    assert len(turns) == 7


def test_iter_turns_unknown_session_returns_empty(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    backend = IdeSessionBackend(root=kiro_root)
    turns = list(backend.iter_turns("nonexistent-uuid"))
    assert turns == []


def test_iter_turns_ordered_by_start_time(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    backend = IdeSessionBackend(root=kiro_root)
    turns = list(backend.iter_turns(SESSION_ID))
    end_timestamps = [t.end_timestamp for t in turns if t.end_timestamp is not None]
    assert end_timestamps == sorted(end_timestamps)


# ── T8: iter_tool_calls ──────────────────────────────────────────────


def test_iter_tool_calls_with_raw_session_id(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    backend = IdeSessionBackend(root=kiro_root)
    calls = list(backend.iter_tool_calls(SESSION_ID))
    assert len(calls) >= 15
    assert all(isinstance(c, ToolCall) for c in calls)


def test_iter_tool_calls_with_composite_session_id(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    backend = IdeSessionBackend(root=kiro_root)
    composite = composite_session_id(SESSION_ID)
    calls = list(backend.iter_tool_calls(composite))
    assert len(calls) >= 15


def test_iter_tool_calls_unique_ids(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    backend = IdeSessionBackend(root=kiro_root)
    calls = list(backend.iter_tool_calls(SESSION_ID))
    ids = [c.tool_use_id for c in calls]
    assert len(set(ids)) == len(ids)


def test_iter_tool_calls_unknown_session_empty(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    backend = IdeSessionBackend(root=kiro_root)
    assert list(backend.iter_tool_calls("nope")) == []


# ── T9: running_sessions (heurística primária) ───────────────────────


def test_running_sessions_returns_session_when_running_exists(tmp_path):
    kiro_root = build_ide_layout(tmp_path, include_running=True)
    backend = IdeSessionBackend(root=kiro_root)
    running = backend.running_sessions()
    assert len(running) == 1
    assert running[0].is_active


def test_running_sessions_empty_when_no_running(tmp_path):
    kiro_root = build_ide_layout(tmp_path, include_running=False)
    backend = IdeSessionBackend(root=kiro_root)
    assert backend.running_sessions() == []


def test_running_sessions_empty_when_unavailable(tmp_path):
    backend = IdeSessionBackend(root=tmp_path / "nope")
    assert backend.running_sessions() == []


# ── T9: running_sessions_fallback (mtime + active) ───────────────────


def test_running_sessions_fallback_includes_fresh_session(tmp_path):
    """Sessão acabada de criar deve cair no fallback."""
    kiro_root = build_ide_layout(tmp_path, include_running=False)
    backend = IdeSessionBackend(root=kiro_root)
    # Threshold permissivo
    fresh = backend.running_sessions_fallback(threshold_seconds=300)
    assert len(fresh) == 1


def test_running_sessions_fallback_excludes_stale(tmp_path):
    """Threshold curto deve excluir sessões de algumas horas atrás."""
    kiro_root = build_ide_layout(tmp_path, include_running=False)
    backend = IdeSessionBackend(root=kiro_root)
    # Tornar o arquivo "antigo" mexendo no mtime
    ws = backend.list_workspaces()[0]
    sess_path = ws.fs_dir / f"{SESSION_ID}.json"
    old_time = time.time() - 3600  # 1h atrás
    import os

    os.utime(sess_path, (old_time, old_time))
    fresh = backend.running_sessions_fallback(threshold_seconds=60)
    assert fresh == []


def test_running_sessions_fallback_empty_when_unavailable(tmp_path):
    backend = IdeSessionBackend(root=tmp_path / "nope")
    assert backend.running_sessions_fallback() == []


# ── Integration: data_age + capabilities ─────────────────────────────


def test_data_age_under_one_minute_for_fresh_fixture(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    backend = IdeSessionBackend(root=kiro_root)
    age = backend.data_age()
    assert age is not None
    assert age < 60


def test_capabilities_unchanged_after_api_addition(tmp_path):
    """Sanity: T8/T9 não alteram o conjunto de capabilities."""
    from kiro_dash.backends import Capability

    kiro_root = build_ide_layout(tmp_path)
    backend = IdeSessionBackend(root=kiro_root)
    assert backend.capabilities() == {
        Capability.SESSIONS,
        Capability.TURNS,
        Capability.TOOL_CALLS,
        Capability.RUNNING,
    }
