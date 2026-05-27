"""Tests T2 frente R — snapshots v2 + migração transparente v1→v2."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from kiro_dash.models import Session, Turn
from kiro_dash.snapshots import (
    SCHEMA_VERSION,
    SnapshotPaths,
    SnapshotSchemaError,
    _detect_session_source,
    _migrate_snapshot_in_memory,
    build_snapshot,
    read_snapshot,
    write_snapshot,
)


def _mk_turn(end_dt: datetime, credits: float = 0.5) -> Turn:
    return Turn(
        end_timestamp=end_dt,
        agent_name="kiro_default",
        parent_agent_id=None,
        duration=timedelta(seconds=1),
        end_reason="UserTurnEnd",
        builtin_tool_uses=0,
        number_of_cycles=1,
        context_usage_pct=10.0,
        credits=credits,
    )


def _mk_session(sid: str, end_dt: datetime, credits: float = 0.5) -> Session:
    return Session(
        session_id=sid,
        title=f"title-{sid[:4]}",
        agent_name="kiro_default",
        model_id="auto",
        rate_multiplier=1.0,
        context_window_tokens=200_000,
        cwd="/tmp",
        created_at=end_dt - timedelta(seconds=10),
        updated_at=end_dt,
        version="v1",
        session_created_reason=None,
        is_active=False,
        turns=[_mk_turn(end_dt, credits)],
    )


# ── _detect_session_source helper ────────────────────────────────────


def test_detect_source_cli_raw_uuid():
    assert _detect_session_source("abc-123") == ("cli", "cli:abc-123")


def test_detect_source_ide_composite():
    assert _detect_session_source("ide-sessions:abc-123") == (
        "ide-sessions",
        "ide-sessions:abc-123",
    )


def test_detect_source_other_slug():
    """Qualquer slug:uuid é preservado."""
    assert _detect_session_source("future:xyz") == ("future", "future:xyz")


# ── build_snapshot v2 ────────────────────────────────────────────────


def test_build_snapshot_schema_version_is_2():
    today = date.today()
    end = datetime.combine(today, datetime.min.time(), timezone.utc) + timedelta(hours=12)
    sessions = [_mk_session("cli-uuid-001", end)]
    snap = build_snapshot(sessions, d=today, host="testhost")
    assert snap["schema_version"] == 2


def test_build_snapshot_by_session_has_internal_id_and_source():
    today = date.today()
    end = datetime.combine(today, datetime.min.time(), timezone.utc) + timedelta(hours=12)
    sessions = [_mk_session("cli-uuid-001", end)]
    snap = build_snapshot(sessions, d=today, host="testhost")
    assert "by_session" in snap
    assert len(snap["by_session"]) >= 1
    entry = snap["by_session"][0]
    assert "internal_session_id" in entry
    assert "source" in entry
    assert entry["source"] == "cli"
    assert entry["internal_session_id"].startswith("cli:")


def test_build_snapshot_ide_session_has_ide_source():
    today = date.today()
    end = datetime.combine(today, datetime.min.time(), timezone.utc) + timedelta(hours=12)
    sessions = [_mk_session("ide-sessions:abc-123", end)]
    snap = build_snapshot(sessions, d=today, host="testhost")
    entry = snap["by_session"][0]
    assert entry["source"] == "ide-sessions"
    assert entry["internal_session_id"] == "ide-sessions:abc-123"


def test_build_snapshot_mixed_sources():
    today = date.today()
    end = datetime.combine(today, datetime.min.time(), timezone.utc) + timedelta(hours=12)
    sessions = [
        _mk_session("cli-uuid-001", end, credits=1.0),
        _mk_session("ide-sessions:abc-123", end, credits=2.0),
    ]
    snap = build_snapshot(sessions, d=today, host="testhost")
    sources = {entry["source"] for entry in snap["by_session"]}
    assert sources == {"cli", "ide-sessions"}
    assert snap["totals"]["sessions"] == 2


# ── read_snapshot — migração v1 → v2 ────────────────────────────────


def test_read_snapshot_v1_legacy_migrates_in_memory(tmp_path):
    """Snapshot v1 antigo é lido transparentemente como v2."""
    today = date.today()
    paths = SnapshotPaths(root=tmp_path)
    paths.root.mkdir(parents=True, exist_ok=True)
    target = paths.for_date(today, "legacy-host")
    legacy_v1 = {
        "schema_version": 1,
        "local_date": today.isoformat(),
        "tz_offset": "-03:00",
        "captured_at": "2026-05-27T12:00:00Z",
        "captured_by_host": "legacy-host",
        "totals": {"credits": 1.5, "turns": 3, "sessions": 1},
        "by_model": [],
        "by_project": [],
        "by_agent_pair": [],
        "by_session": [
            {
                "label": "abc12345 my-title",
                "credits": 1.5,
                "turns": 3,
                "sessions": 1,
                "duration_secs": 10,
                "tool_uses": 0,
            }
        ],
        "by_tool": [],
    }
    target.write_text(json.dumps(legacy_v1))
    snap = read_snapshot(today, paths=paths)
    assert snap is not None
    assert snap["schema_version"] == SCHEMA_VERSION
    entry = snap["by_session"][0]
    assert entry["source"] == "cli"
    assert entry["internal_session_id"] == "cli:abc12345"


def test_read_snapshot_no_schema_version_treated_as_v1(tmp_path):
    today = date.today()
    paths = SnapshotPaths(root=tmp_path)
    paths.root.mkdir(parents=True, exist_ok=True)
    target = paths.for_date(today, "ancient-host")
    ancient = {
        "local_date": today.isoformat(),
        "tz_offset": "-03:00",
        "captured_at": "2026-05-27T12:00:00Z",
        "captured_by_host": "ancient-host",
        "totals": {"credits": 0.5, "turns": 1, "sessions": 1},
        "by_session": [{"label": "deadbeef", "credits": 0.5, "turns": 1, "sessions": 1, "duration_secs": 5, "tool_uses": 0}],
        "by_model": [],
        "by_project": [],
        "by_agent_pair": [],
        "by_tool": [],
    }
    target.write_text(json.dumps(ancient))
    snap = read_snapshot(today, paths=paths)
    assert snap is not None
    assert snap["schema_version"] == SCHEMA_VERSION
    assert snap["by_session"][0]["source"] == "cli"


def test_read_snapshot_v2_pure_passes_through(tmp_path):
    today = date.today()
    paths = SnapshotPaths(root=tmp_path)
    paths.root.mkdir(parents=True, exist_ok=True)
    target = paths.for_date(today, "modern-host")
    pure_v2 = {
        "schema_version": 2,
        "local_date": today.isoformat(),
        "tz_offset": "-03:00",
        "captured_at": "2026-05-27T12:00:00Z",
        "captured_by_host": "modern-host",
        "totals": {"credits": 2.0, "turns": 4, "sessions": 2},
        "by_model": [],
        "by_project": [],
        "by_agent_pair": [],
        "by_session": [
            {
                "label": "abc cli session",
                "internal_session_id": "cli:abc-123",
                "source": "cli",
                "credits": 1.0,
                "turns": 2,
                "sessions": 1,
                "duration_secs": 5,
                "tool_uses": 0,
            },
            {
                "label": "def ide session",
                "internal_session_id": "ide-sessions:def-456",
                "source": "ide-sessions",
                "credits": 1.0,
                "turns": 2,
                "sessions": 1,
                "duration_secs": 5,
                "tool_uses": 0,
            },
        ],
        "by_tool": [],
    }
    target.write_text(json.dumps(pure_v2))
    snap = read_snapshot(today, paths=paths)
    assert snap is not None
    assert snap["schema_version"] == 2
    sources = {e["source"] for e in snap["by_session"]}
    assert sources == {"cli", "ide-sessions"}


def test_read_snapshot_future_version_raises(tmp_path):
    """schema_version > SCHEMA_VERSION → erro estruturado."""
    today = date.today()
    paths = SnapshotPaths(root=tmp_path)
    paths.root.mkdir(parents=True, exist_ok=True)
    target = paths.for_date(today, "future-host")
    future = {
        "schema_version": 99,
        "local_date": today.isoformat(),
        "tz_offset": "-03:00",
        "captured_at": "2026-05-27T12:00:00Z",
        "captured_by_host": "future-host",
        "totals": {"credits": 0, "turns": 0, "sessions": 0},
    }
    target.write_text(json.dumps(future))
    with pytest.raises(SnapshotSchemaError, match="schema_version=99"):
        read_snapshot(today, paths=paths)


# ── _migrate_snapshot_in_memory unit tests ───────────────────────────


def test_migrate_v1_idempotent_via_v2_input():
    """Aplicar migração em snapshot já v2 não muda nada."""
    snap_v2 = {
        "schema_version": 2,
        "by_session": [
            {"label": "x", "internal_session_id": "cli:x", "source": "cli"}
        ],
    }
    out = _migrate_snapshot_in_memory(snap_v2)
    assert out == snap_v2


def test_migrate_preserves_other_fields():
    snap_v1 = {
        "schema_version": 1,
        "local_date": "2026-05-01",
        "totals": {"credits": 5.0, "turns": 10, "sessions": 2},
        "by_session": [],
    }
    out = _migrate_snapshot_in_memory(snap_v1)
    assert out["local_date"] == "2026-05-01"
    assert out["totals"]["credits"] == 5.0


# ── write/read roundtrip ────────────────────────────────────────────


def test_write_then_read_roundtrip_v2(tmp_path):
    today = date.today()
    end = datetime.combine(today, datetime.min.time(), timezone.utc) + timedelta(hours=12)
    sessions = [_mk_session("cli-uuid-001", end)]
    paths = SnapshotPaths(root=tmp_path)
    write_snapshot(sessions, d=today, host="rt-host", paths=paths)
    snap = read_snapshot(today, paths=paths)
    assert snap is not None
    assert snap["schema_version"] == 2
    assert snap["by_session"][0]["source"] == "cli"
