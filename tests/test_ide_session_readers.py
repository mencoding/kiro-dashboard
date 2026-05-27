"""Tests T4-T6 — readers tipados de sessão e execution (frente Q)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from kiro_dash.backends.ide_sessions import (
    EXECUTIONS_CATALOG_FILENAME,
    IdeAction,
    IdeExecution,
    IdeExecutionIndexEntry,
    IdeIntent,
    IdeSession,
    IdeSessionBackend,
    IdeSessionMetadata,
    IdeUsageEntry,
    read_execution,
    read_executions_catalog,
    read_session,
    read_sessions_index,
)
from tests.fixtures.ide.build_ide_layout import (
    DEFAULT_PROFILE_HASH,
    DEFAULT_WORKSPACE_PATH,
    EXEC_CHAT,
    EXEC_DO_COMPLEX,
    EXEC_DO_SIMPLE,
    EXEC_DO_WRITE,
    EXEC_RUNNING,
    EXEC_SPEC_DISPATCH,
    EXEC_SPEC_GENERATION,
    INNER_HASH,
    SESSION_ID,
    build_ide_layout,
)


# ── T4: read_sessions_index + read_session ──────────────────────────


def test_read_sessions_index_returns_one_metadata(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    backend = IdeSessionBackend(root=kiro_root)
    ws = backend.list_workspaces()[0]
    metas = read_sessions_index(ws.fs_dir)
    assert len(metas) == 1
    m = metas[0]
    assert isinstance(m, IdeSessionMetadata)
    assert m.session_id == SESSION_ID
    assert m.title == "Test Fixture Session"
    assert m.workspace_directory == DEFAULT_WORKSPACE_PATH
    assert isinstance(m.date_created, datetime)
    assert m.date_created.tzinfo is not None  # UTC


def test_read_sessions_index_empty_when_missing(tmp_path):
    assert read_sessions_index(tmp_path / "nope") == []


def test_read_sessions_index_empty_when_corrupt(tmp_path):
    (tmp_path / "sessions.json").write_text("{not json")
    assert read_sessions_index(tmp_path) == []


def test_read_sessions_index_empty_when_not_list(tmp_path):
    (tmp_path / "sessions.json").write_text('{"sessions": []}')
    assert read_sessions_index(tmp_path) == []


def test_read_session_returns_typed_model(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    backend = IdeSessionBackend(root=kiro_root)
    ws = backend.list_workspaces()[0]
    sess = read_session(SESSION_ID, ws.fs_dir)
    assert sess is not None
    assert isinstance(sess, IdeSession)
    assert sess.session_id == SESSION_ID
    assert sess.workspace_path == DEFAULT_WORKSPACE_PATH
    assert sess.session_type == "vibe"
    assert sess.autonomy_mode == "Autopilot"
    assert sess.selected_model == "auto"
    assert sess.default_model_title == "Agent"
    assert sess.history_length == 2
    assert sess.context_usage_percentage > 0
    assert isinstance(sess.mtime, datetime)


def test_read_session_history_does_not_leak_content(tmp_path):
    """O reader nunca expõe ``message`` ou ``content``; só presença."""
    kiro_root = build_ide_layout(tmp_path)
    backend = IdeSessionBackend(root=kiro_root)
    ws = backend.list_workspaces()[0]
    sess = read_session(SESSION_ID, ws.fs_dir)
    assert sess is not None
    for h in sess.history:
        # IdeHistoryItem só tem flags + count
        assert hasattr(h, "has_message")
        assert hasattr(h, "has_context_items")
        assert hasattr(h, "has_editor_state")
        assert hasattr(h, "context_items_count")
        # E NADA mais
        from dataclasses import fields
        all_fields = {f.name for f in fields(h)}
        assert all_fields == {
            "has_message",
            "has_context_items",
            "has_editor_state",
            "context_items_count",
        }


def test_read_session_returns_none_when_missing(tmp_path):
    assert read_session("nonexistent-uuid", tmp_path) is None


def test_read_session_returns_none_when_corrupt(tmp_path):
    (tmp_path / "abc.json").write_text("{not json")
    assert read_session("abc", tmp_path) is None


# ── T5: read_executions_catalog ──────────────────────────────────────


def test_read_executions_catalog_returns_seven_entries(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    profile_dir = kiro_root / DEFAULT_PROFILE_HASH
    entries = read_executions_catalog(profile_dir)
    assert len(entries) == 7
    for e in entries:
        assert isinstance(e, IdeExecutionIndexEntry)
        assert e.chat_session_id == SESSION_ID


def test_read_executions_catalog_includes_running_with_endtime_none(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    profile_dir = kiro_root / DEFAULT_PROFILE_HASH
    entries = read_executions_catalog(profile_dir)
    running = [e for e in entries if e.is_running]
    assert len(running) == 1
    assert running[0].execution_id == EXEC_RUNNING
    assert running[0].end_time is None
    assert running[0].duration_ms is None


def test_read_executions_catalog_workflow_types(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    profile_dir = kiro_root / DEFAULT_PROFILE_HASH
    entries = read_executions_catalog(profile_dir)
    types = {e.workflow_type for e in entries}
    assert types == {"chat-agent", "spec-generation"}


def test_read_executions_catalog_succeed_have_duration(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    profile_dir = kiro_root / DEFAULT_PROFILE_HASH
    entries = read_executions_catalog(profile_dir)
    for e in entries:
        if e.status == "succeed":
            assert e.duration_ms is not None
            assert e.duration_ms >= 0


def test_read_executions_catalog_empty_when_missing(tmp_path):
    assert read_executions_catalog(tmp_path / "no_profile") == []


def test_read_executions_catalog_empty_when_corrupt(tmp_path):
    (tmp_path / EXECUTIONS_CATALOG_FILENAME).write_text("garbage")
    assert read_executions_catalog(tmp_path) == []


# ── T6: read_execution (arquivo completo) ────────────────────────────


def test_read_execution_chat_intent_is_chat(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    inner = kiro_root / DEFAULT_PROFILE_HASH / INNER_HASH
    ex = read_execution(inner / EXEC_CHAT)
    assert ex is not None
    assert isinstance(ex, IdeExecution)
    assert ex.workflow_type == "chat-agent"
    assert ex.intent_result is not None
    assert ex.intent_result.classification == "chat"
    assert ex.status == "succeed"
    assert ex.is_running is False
    assert ex.total_credits > 0


def test_read_execution_do_simple_uses_execute_bash(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    inner = kiro_root / DEFAULT_PROFILE_HASH / INNER_HASH
    ex = read_execution(inner / EXEC_DO_SIMPLE)
    assert ex is not None
    assert ex.intent_result is not None
    assert ex.intent_result.classification == "do"
    assert "execute_bash" in ex.all_used_tools


def test_read_execution_do_complex_has_full_lifecycle(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    inner = kiro_root / DEFAULT_PROFILE_HASH / INNER_HASH
    ex = read_execution(inner / EXEC_DO_COMPLEX)
    assert ex is not None
    assert {"read_files", "execute_bash", "control_bash_process", "get_process_output"} <= set(
        ex.all_used_tools
    )


def test_read_execution_do_write_has_fs_write(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    inner = kiro_root / DEFAULT_PROFILE_HASH / INNER_HASH
    ex = read_execution(inner / EXEC_DO_WRITE)
    assert ex is not None
    assert "fs_write" in ex.all_used_tools
    assert "str_replace" in ex.all_used_tools


def test_read_execution_spec_dispatch_has_intent_spec(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    inner = kiro_root / DEFAULT_PROFILE_HASH / INNER_HASH
    ex = read_execution(inner / EXEC_SPEC_DISPATCH)
    assert ex is not None
    assert ex.intent_result is not None
    assert ex.intent_result.classification == "spec"
    action_types = [a.action_type for a in ex.actions]
    assert "specAgent" in action_types
    assert "userInput" in action_types


def test_read_execution_spec_generation_has_no_intent(tmp_path):
    """Decisão #4 do plano Q: spec-generation é sub-execução, sem classifier."""
    kiro_root = build_ide_layout(tmp_path)
    inner = kiro_root / DEFAULT_PROFILE_HASH / INNER_HASH
    ex = read_execution(inner / EXEC_SPEC_GENERATION)
    assert ex is not None
    assert ex.workflow_type == "spec-generation"
    assert ex.intent_result is None
    assert "invoke_sub_agent" in ex.all_used_tools


def test_read_execution_running_has_endtime_none(tmp_path):
    """Decisão #10 do plano Q: heurística live via status=running + endTime=0."""
    kiro_root = build_ide_layout(tmp_path)
    inner = kiro_root / DEFAULT_PROFILE_HASH / INNER_HASH
    ex = read_execution(inner / EXEC_RUNNING)
    assert ex is not None
    assert ex.is_running
    assert ex.end_time is None
    assert ex.workflow_type == "spec-generation"


def test_read_execution_returns_none_when_missing(tmp_path):
    assert read_execution(tmp_path / "no_such_file") is None


def test_read_execution_returns_none_when_corrupt(tmp_path):
    p = tmp_path / "exec"
    p.write_text("{not json")
    assert read_execution(p) is None


def test_read_execution_actions_typed(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    inner = kiro_root / DEFAULT_PROFILE_HASH / INNER_HASH
    ex = read_execution(inner / EXEC_DO_SIMPLE)
    assert ex is not None
    for a in ex.actions:
        assert isinstance(a, IdeAction)
        assert a.action_id
        assert a.action_type
        assert a.action_state
        assert isinstance(a.emitted_at, datetime)


def test_read_execution_usage_summary_typed(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    inner = kiro_root / DEFAULT_PROFILE_HASH / INNER_HASH
    ex = read_execution(inner / EXEC_DO_COMPLEX)
    assert ex is not None
    assert len(ex.usage_summary) >= 1
    for u in ex.usage_summary:
        assert isinstance(u, IdeUsageEntry)
        assert u.usage > 0
        assert u.unit == "credit"
        assert u.unit_plural == "credits"
        assert isinstance(u.used_tools, list)


def test_read_execution_total_credits_sums_phases(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    inner = kiro_root / DEFAULT_PROFILE_HASH / INNER_HASH
    ex = read_execution(inner / EXEC_DO_COMPLEX)
    assert ex is not None
    expected = sum(u.usage for u in ex.usage_summary)
    assert ex.total_credits == pytest.approx(expected)
    assert ex.total_credits > 0.6  # do_complex tem ~0.66


def test_read_execution_intent_full_payload(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    inner = kiro_root / DEFAULT_PROFILE_HASH / INNER_HASH
    ex = read_execution(inner / EXEC_DO_SIMPLE)
    assert ex is not None
    intent = ex.intent_result
    assert isinstance(intent, IdeIntent)
    assert intent.classification == "do"
    assert isinstance(intent.final_intent, dict)
    assert isinstance(intent.llm_intent, dict)
    assert isinstance(intent.local_intent, dict)


# ── Integration: readers através do backend ─────────────────────────


def test_backend_read_session_through_workspace(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    backend = IdeSessionBackend(root=kiro_root)
    ws = backend.list_workspaces()[0]
    metas = read_sessions_index(ws.fs_dir)
    assert metas
    sess = read_session(metas[0].session_id, ws.fs_dir)
    assert sess is not None
    assert sess.session_id == metas[0].session_id


def test_backend_read_executions_through_profile_hash(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    backend = IdeSessionBackend(root=kiro_root)
    profile_dirs = list(backend.iter_profile_hash_dirs())
    assert profile_dirs
    entries = read_executions_catalog(profile_dirs[0])
    assert len(entries) == 7
