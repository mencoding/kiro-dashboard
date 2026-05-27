"""Testes do CliJsonBackend (wrapper sobre parser.py)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from kiro_dash.backends import Capability
from kiro_dash.backends.cli_json import CliJsonBackend


def _write_minimal_session(sessions_dir: Path, sid: str) -> Path:
    """Cria session JSON mínimo aceito pelo parser para testes."""
    sessions_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "session_id": sid,
        "session_state": {
            "agent_name": "nyx",
            "model_info": {"model_id": "auto"},
            "conversation_metadata": {
                "user_turn_metadatas": [],
            },
        },
        "created_at": "2026-05-27T10:00:00Z",
        "updated_at": "2026-05-27T10:05:00Z",
        "version": "v1",
    }
    p = sessions_dir / f"{sid}.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_slug_and_capabilities():
    b = CliJsonBackend(sessions_dir=Path("/nonexistent"))
    assert b.slug == "cli"
    caps = b.capabilities()
    assert Capability.SESSIONS in caps
    assert Capability.TURNS in caps
    assert Capability.TOOL_CALLS in caps
    assert Capability.RUNNING in caps
    assert Capability.USAGE_STATE not in caps


def test_is_available_false_for_missing_dir(tmp_path):
    b = CliJsonBackend(sessions_dir=tmp_path / "no_kiro")
    assert b.is_available() is False


def test_is_available_true_for_existing_dir(tmp_path):
    sessions_dir = tmp_path / "kiro" / "sessions" / "cli"
    sessions_dir.mkdir(parents=True)
    b = CliJsonBackend(sessions_dir=sessions_dir)
    assert b.is_available() is True


def test_data_age_default_none(tmp_path):
    b = CliJsonBackend(sessions_dir=tmp_path)
    assert b.data_age() is None


def test_list_session_paths_empty(tmp_path):
    b = CliJsonBackend(sessions_dir=tmp_path)
    assert b.list_session_paths() == []


def test_list_and_load_sessions(tmp_path):
    _write_minimal_session(tmp_path, "11111111-1111-1111-1111-111111111111")
    _write_minimal_session(tmp_path, "22222222-2222-2222-2222-222222222222")
    b = CliJsonBackend(sessions_dir=tmp_path)
    paths = b.list_session_paths()
    assert len(paths) == 2
    sessions = b.load_all_sessions()
    assert len(sessions) == 2
    ids = {s.session_id for s in sessions}
    assert ids == {
        "11111111-1111-1111-1111-111111111111",
        "22222222-2222-2222-2222-222222222222",
    }


def test_find_by_prefix(tmp_path):
    _write_minimal_session(tmp_path, "abcdef00-0000-0000-0000-000000000001")
    b = CliJsonBackend(sessions_dir=tmp_path)
    found = b.find_by_prefix("abcdef00")
    assert found is not None
    assert "abcdef00" in found.name


def test_running_session_ids_with_lock(tmp_path):
    sid = "abcdef00-0000-0000-0000-000000000002"
    _write_minimal_session(tmp_path, sid)
    # Lock file body: {"pid":N,"started_at":"..."}
    (tmp_path / f"{sid}.lock").write_text(
        '{"pid":12345,"started_at":"2026-05-27T17:00:00Z"}',
        encoding="utf-8",
    )
    b = CliJsonBackend(sessions_dir=tmp_path)
    running = b.running_session_ids()
    assert running == [sid]


def test_running_session_ids_empty_when_no_locks(tmp_path):
    sid = "abcdef00-0000-0000-0000-000000000003"
    _write_minimal_session(tmp_path, sid)
    b = CliJsonBackend(sessions_dir=tmp_path)
    assert b.running_session_ids() == []
