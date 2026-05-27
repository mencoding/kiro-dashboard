"""Cobertura de leitura de lockfile."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from kiro_dash.parser import read_lock


def test_read_lock_returns_none_when_absent(tmp_path):
    sid = "abc123"
    assert read_lock(sid, sessions_dir=tmp_path) is None


def test_read_lock_parses_valid(tmp_path):
    sid = "abc123"
    lock = tmp_path / f"{sid}.lock"
    lock.write_text(json.dumps({
        "pid": 12345,
        "started_at": "2026-05-26T20:00:00.000000000Z",
    }))
    info = read_lock(sid, sessions_dir=tmp_path)
    assert info is not None
    assert info.pid == 12345
    assert info.started_at == datetime(2026, 5, 26, 20, 0, tzinfo=timezone.utc)


def test_read_lock_returns_none_on_invalid_json(tmp_path):
    sid = "abc"
    lock = tmp_path / f"{sid}.lock"
    lock.write_text("not json")
    assert read_lock(sid, sessions_dir=tmp_path) is None
