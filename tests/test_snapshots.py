"""Cobertura de snapshots."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from kiro_dash.snapshots import (
    SnapshotPaths,
    build_snapshot,
    read_snapshot,
    snapshots_dir_default,
    write_snapshot,
)
from tests.fixtures.sessions_synthetic import make_session, make_turn

FAKE_NOW = datetime(2026, 5, 17, 15, 0, tzinfo=timezone.utc)
# 12h local BRT (UTC-3) = 15h UTC
_BRT = timezone(timedelta(hours=-3))


def _make_sample(d: date):
    """Dois turns no dia d local (BRT)."""
    base_local = datetime.combine(d, datetime.min.time(), tzinfo=_BRT).replace(hour=12)
    base_utc = base_local.astimezone(timezone.utc)
    return [
        make_session(
            session_id="aaaa",
            cwd="/proj/alfa",
            model_id="claude-opus-4.7",
            is_active=False,
            turns=[
                make_turn(end_timestamp=base_utc, credits=3.0),
                make_turn(end_timestamp=base_utc + timedelta(minutes=5), credits=2.0),
            ],
        ),
    ]


def test_snapshots_dir_default_uses_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert snapshots_dir_default() == tmp_path / "kiro-dash" / "snapshots"


def test_build_snapshot_aggregates_corretamente(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    sessions = _make_sample(date(2026, 5, 16))
    snap = build_snapshot(sessions, d=date(2026, 5, 16), host="test-host", now=FAKE_NOW)
    assert snap["schema_version"] == 2
    assert snap["local_date"] == "2026-05-16"
    assert snap["captured_by_host"] == "test-host"
    assert snap["totals"]["credits"] == 5.0
    assert snap["totals"]["turns"] == 2
    assert snap["totals"]["sessions"] == 1
    assert any(m["label"] == "claude-opus-4.7" for m in snap["by_model"])


def test_write_then_read_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    paths = SnapshotPaths(root=tmp_path / "snaps")
    sessions = _make_sample(date(2026, 5, 16))
    write_snapshot(sessions, d=date(2026, 5, 16), host="h1", paths=paths, now=FAKE_NOW)
    out = read_snapshot(date(2026, 5, 16), paths=paths)
    assert out is not None
    assert out["totals"]["credits"] == 5.0


def test_read_returns_none_when_missing(tmp_path):
    paths = SnapshotPaths(root=tmp_path)
    assert read_snapshot(date(2026, 5, 16), paths=paths) is None


def test_read_merges_multiple_hosts(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    paths = SnapshotPaths(root=tmp_path / "snaps")
    sessions_a = _make_sample(date(2026, 5, 16))
    sessions_b = [
        make_session(
            session_id="bbbb",
            cwd="/proj/beta",
            model_id="auto",
            is_active=False,
            turns=[
                make_turn(
                    end_timestamp=FAKE_NOW - timedelta(days=1, minutes=30),
                    credits=4.0,
                )
            ],
        )
    ]
    write_snapshot(sessions_a, d=date(2026, 5, 16), host="predator", paths=paths, now=FAKE_NOW)
    write_snapshot(sessions_b, d=date(2026, 5, 16), host="work", paths=paths, now=FAKE_NOW)

    merged = read_snapshot(date(2026, 5, 16), paths=paths)
    assert merged is not None
    assert merged["totals"]["credits"] == 9.0
    assert merged["totals"]["sessions"] == 2
    assert "merged_from" in merged
    assert sorted(merged["merged_from"]) == ["predator", "work"]


# ─── Task 2: ensure_snapshots_up_to ──────────────────────────────────────


def test_ensure_snapshots_up_to_gera_dias_faltantes(tmp_path, monkeypatch):
    """Self-healing: ensure_snapshots_up_to gera tudo que falta."""
    from kiro_dash.snapshots import ensure_snapshots_up_to

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    paths = SnapshotPaths(root=tmp_path / "snaps")
    sessions = _make_sample(date(2026, 5, 16))

    created = ensure_snapshots_up_to(
        date(2026, 5, 16),
        sessions,
        paths=paths,
        host="h1",
        now=FAKE_NOW,
        lookback_days=7,
    )
    assert any("2026-05-16" in str(p) for p in created)


def test_ensure_snapshots_up_to_idempotente(tmp_path, monkeypatch):
    """Reexecutar não recria snapshots existentes."""
    from kiro_dash.snapshots import ensure_snapshots_up_to

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    paths = SnapshotPaths(root=tmp_path / "snaps")
    sessions = _make_sample(date(2026, 5, 16))

    ensure_snapshots_up_to(date(2026, 5, 16), sessions, paths=paths, host="h1", now=FAKE_NOW)
    created_2 = ensure_snapshots_up_to(
        date(2026, 5, 16), sessions, paths=paths, host="h1", now=FAKE_NOW
    )
    assert created_2 == []


def test_ensure_snapshots_nao_inclui_hoje_nem_ontem_se_target_eh_anteontem(tmp_path, monkeypatch):
    """Target ``up_to=anteontem`` não cria snapshot de hoje nem de ontem."""
    from kiro_dash.snapshots import ensure_snapshots_up_to

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    paths = SnapshotPaths(root=tmp_path / "snaps")
    target = date(2026, 5, 15)
    sessions = _make_sample(date(2026, 5, 15))
    ensure_snapshots_up_to(target, sessions, paths=paths, host="h1", now=FAKE_NOW)

    files = list(paths.root.glob("*.json"))
    assert not any("2026-05-16" in str(p) or "2026-05-17" in str(p) for p in files)
