"""Tests T7 — mapper IDE → tipo interno (frente Q)."""
from __future__ import annotations

from datetime import timedelta

from kiro_dash.backends.ide_mapper import (
    AGENT_NAME,
    DEFAULT_CONTEXT_WINDOW_TOKENS,
    DEFAULT_RATE_MULTIPLIER,
    SCHEMA_VERSION,
    SOURCE_SLUG,
    composite_session_id,
    normalize_model_id,
    to_session,
    to_tool_calls,
    to_tool_calls_for_session,
    to_turn,
)
from kiro_dash.backends.ide_sessions import (
    IdeSessionBackend,
    read_execution,
    read_session,
    read_sessions_index,
)
from kiro_dash.jsonl_parser import ToolCall
from kiro_dash.models import Session, Turn
from tests.fixtures.ide.build_ide_layout import (
    DEFAULT_PROFILE_HASH,
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


def _load_execution(kiro_root, exec_id):
    return read_execution(kiro_root / DEFAULT_PROFILE_HASH / INNER_HASH / exec_id)


def _load_all_executions(kiro_root):
    return [
        _load_execution(kiro_root, eid)
        for eid in [
            EXEC_CHAT,
            EXEC_DO_SIMPLE,
            EXEC_DO_COMPLEX,
            EXEC_DO_WRITE,
            EXEC_SPEC_DISPATCH,
            EXEC_SPEC_GENERATION,
            EXEC_RUNNING,
        ]
    ]


def _load_session(kiro_root):
    backend = IdeSessionBackend(root=kiro_root)
    ws = backend.list_workspaces()[0]
    return read_session(SESSION_ID, ws.fs_dir)


# ── Helpers ──────────────────────────────────────────────────────────


def test_composite_session_id():
    assert composite_session_id("abc-123") == "ide-sessions:abc-123"
    assert SOURCE_SLUG == "ide-sessions"


def test_normalize_model_id_auto():
    assert normalize_model_id("auto") == "kiro:auto"


def test_normalize_model_id_specific():
    assert normalize_model_id("claude-opus-4.7") == "claude-opus-4.7"


def test_normalize_model_id_empty_falls_back_to_auto():
    assert normalize_model_id("") == "kiro:auto"


# ── to_turn ──────────────────────────────────────────────────────────


def test_to_turn_chat_returns_typed_turn(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    ex = _load_execution(kiro_root, EXEC_CHAT)
    turn = to_turn(ex)
    assert isinstance(turn, Turn)
    assert turn.agent_name == AGENT_NAME
    assert turn.parent_agent_id is None
    assert turn.end_reason == "succeed"
    assert turn.credits > 0
    assert turn.builtin_tool_uses == 0  # chat sem tools
    assert turn.number_of_cycles == 1  # 1 model action
    assert turn.duration > timedelta(0)


def test_to_turn_do_simple_counts_one_tool_use(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    ex = _load_execution(kiro_root, EXEC_DO_SIMPLE)
    turn = to_turn(ex)
    assert turn.builtin_tool_uses == 1  # 1 fase com [execute_bash]
    assert turn.number_of_cycles == 2  # 2 model actions


def test_to_turn_do_complex_counts_multiple_tools(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    ex = _load_execution(kiro_root, EXEC_DO_COMPLEX)
    turn = to_turn(ex)
    # 7 fases não-init: read_files, execute_bash×2, control_bash_process,
    # get_process_output×2 = 6 fases com tools (cada uma 1 tool).
    # Total tool_uses = sum dos lens.
    assert turn.builtin_tool_uses >= 4
    assert turn.credits > 0.5  # do_complex tem ~0.66
    assert turn.duration > timedelta(seconds=10)


def test_to_turn_running_has_zero_duration(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    ex = _load_execution(kiro_root, EXEC_RUNNING)
    turn = to_turn(ex)
    assert turn.end_timestamp is None
    assert turn.duration == timedelta(0)
    assert turn.end_reason == "running"


def test_to_turn_credits_match_total(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    ex = _load_execution(kiro_root, EXEC_DO_WRITE)
    turn = to_turn(ex)
    assert turn.credits == ex.total_credits


# ── to_session ───────────────────────────────────────────────────────


def test_to_session_roundtrip(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    ide_sess = _load_session(kiro_root)
    assert ide_sess is not None
    execs = _load_all_executions(kiro_root)
    session = to_session(ide_sess, execs)
    assert isinstance(session, Session)
    assert session.session_id == f"ide-sessions:{SESSION_ID}"
    assert session.agent_name == AGENT_NAME
    assert session.model_id == "kiro:auto"
    assert session.rate_multiplier == DEFAULT_RATE_MULTIPLIER
    assert session.context_window_tokens == DEFAULT_CONTEXT_WINDOW_TOKENS
    assert session.cwd == ide_sess.workspace_path
    assert session.version == SCHEMA_VERSION
    assert len(session.turns) == 7
    assert session.is_active is True  # tem 1 execution running


def test_to_session_inactive_when_no_running(tmp_path):
    kiro_root = build_ide_layout(tmp_path, include_running=False)
    ide_sess = _load_session(kiro_root)
    assert ide_sess is not None
    execs = [
        e
        for e in _load_all_executions(kiro_root)
        if e is not None
    ]
    session = to_session(ide_sess, execs)
    assert session.is_active is False


def test_to_session_total_credits_aggregates_executions(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    ide_sess = _load_session(kiro_root)
    assert ide_sess is not None
    execs = _load_all_executions(kiro_root)
    session = to_session(ide_sess, execs)
    expected_total = sum(e.total_credits for e in execs)
    assert abs(session.total_credits - expected_total) < 1e-6


def test_to_session_title_preserved(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    ide_sess = _load_session(kiro_root)
    assert ide_sess is not None
    session = to_session(ide_sess, _load_all_executions(kiro_root))
    assert session.title == "Test Fixture Session"


def test_to_session_empty_title_becomes_none():
    """Empty title from IDE should map to None (Session.title is Optional)."""
    from datetime import datetime, timezone

    from kiro_dash.backends.ide_sessions import IdeSession

    ide_sess = IdeSession(
        session_id="x",
        title="",  # vazio
        workspace_path="/tmp",
        date_created=datetime.now(timezone.utc),
        session_type="vibe",
        autonomy_mode="Autopilot",
        selected_model="auto",
        default_model_title=None,
        history=[],
        context_usage_percentage=0.0,
        mtime=datetime.now(timezone.utc),
    )
    session = to_session(ide_sess, [])
    assert session.title is None


# ── to_tool_calls ────────────────────────────────────────────────────


def test_to_tool_calls_chat_returns_empty(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    ex = _load_execution(kiro_root, EXEC_CHAT)
    calls = to_tool_calls(ex)
    assert calls == []


def test_to_tool_calls_do_simple_returns_one_execute_bash(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    ex = _load_execution(kiro_root, EXEC_DO_SIMPLE)
    calls = to_tool_calls(ex)
    assert len(calls) == 1
    c = calls[0]
    assert isinstance(c, ToolCall)
    assert c.name == "execute_bash"
    assert c.status == "success"
    assert c.session_id == SESSION_ID  # raw, sem prefixo
    assert c.input_keys == []
    assert c.error_summary is None
    assert c.tool_use_id.startswith(ex.execution_id)


def test_to_tool_calls_do_complex_has_full_set(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    ex = _load_execution(kiro_root, EXEC_DO_COMPLEX)
    calls = to_tool_calls(ex)
    names = [c.name for c in calls]
    assert names.count("execute_bash") == 2
    assert names.count("get_process_output") == 2
    assert "read_files" in names
    assert "control_bash_process" in names


def test_to_tool_calls_do_write_includes_str_replace_and_fs_write(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    ex = _load_execution(kiro_root, EXEC_DO_WRITE)
    calls = to_tool_calls(ex)
    names = {c.name for c in calls}
    assert "fs_write" in names
    assert "str_replace" in names
    assert "getDiagnostics" in names


def test_to_tool_calls_running_status_unknown(tmp_path):
    """Execution running → status=unknown nas tool calls."""
    kiro_root = build_ide_layout(tmp_path)
    ex = _load_execution(kiro_root, EXEC_RUNNING)
    calls = to_tool_calls(ex)
    assert calls  # tem invoke_sub_agent
    assert all(c.status == "unknown" for c in calls)


def test_to_tool_calls_unique_tool_use_ids(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    ex = _load_execution(kiro_root, EXEC_DO_COMPLEX)
    calls = to_tool_calls(ex)
    ids = [c.tool_use_id for c in calls]
    assert len(set(ids)) == len(ids)  # todos únicos


# ── to_tool_calls_for_session ────────────────────────────────────────


def test_to_tool_calls_for_session_concatenates(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    execs = _load_all_executions(kiro_root)
    all_calls = to_tool_calls_for_session(execs)
    # chat: 0; do_simple: 1; do_complex: ~6; do_write: ~4; spec_dispatch: 0;
    # spec_generation: ~5; running: 1
    assert len(all_calls) >= 15
    # IDs continuam únicos cross-execution
    ids = [c.tool_use_id for c in all_calls]
    assert len(set(ids)) == len(ids)
