"""Integração parser ↔ cache."""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from kiro_dash.parser import load_session_file


@pytest.fixture
def isolated_cache(tmp_path, monkeypatch):
    """Substitui o singleton de cache por um sob tmp_path."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    import kiro_dash.cache as cmod

    cmod._sessions_cache = None
    cmod._jsonl_cache = None
    yield
    cmod._sessions_cache = None
    cmod._jsonl_cache = None


def _write_session(path: Path) -> None:
    payload = {
        "session_id": str(path.stem),
        "title": "x",
        "cwd": "/tmp",
        "created_at": "2026-05-26T00:00:00Z",
        "updated_at": "2026-05-26T00:00:00Z",
        "session_state": {
            "version": "1",
            "agent_name": "nyx",
            "rts_model_state": {
                "model_info": {
                    "model_id": "claude-opus-4.7",
                    "rate_multiplier": 5.0,
                    "context_window_tokens": 200000,
                }
            },
            "conversation_metadata": {"user_turn_metadatas": []},
        },
    }
    path.write_text(json.dumps(payload))


def test_second_load_hits_cache(tmp_path, isolated_cache):
    p = tmp_path / "abc.json"
    _write_session(p)

    s1 = load_session_file(p)
    assert s1 is not None

    # On cache hit, the source file should NOT be opened again.
    # We track opens of the source path specifically.
    original_open = Path.open

    opens_of_source = []

    def tracking_open(self, *args, **kwargs):
        if self == p:
            opens_of_source.append(self)
        return original_open(self, *args, **kwargs)

    with patch.object(Path, "open", tracking_open):
        s2 = load_session_file(p)
        assert s2 is not None
        assert s2.session_id == s1.session_id
        assert opens_of_source == []


def test_cache_invalidates_after_mtime_change(tmp_path, isolated_cache):
    p = tmp_path / "abc.json"
    _write_session(p)

    load_session_file(p)
    time.sleep(0.01)
    p.write_text(p.read_text())  # touch — changes mtime

    original_open = Path.open
    opens_of_source = []

    def tracking_open(self, *args, **kwargs):
        if self == p:
            opens_of_source.append(self)
        return original_open(self, *args, **kwargs)

    with patch.object(Path, "open", tracking_open):
        load_session_file(p)
        assert len(opens_of_source) == 1  # mtime changed, must re-read


def test_active_session_bypasses_cache(tmp_path, isolated_cache):
    p = tmp_path / "abc.json"
    _write_session(p)
    lock = p.with_suffix(".lock")
    lock.write_text('{"pid":1}')

    load_session_file(p)  # would populate if not active

    original_open = Path.open
    opens_of_source = []

    def tracking_open(self, *args, **kwargs):
        if self == p:
            opens_of_source.append(self)
        return original_open(self, *args, **kwargs)

    with patch.object(Path, "open", tracking_open):
        load_session_file(p)
        assert len(opens_of_source) == 1  # active session always re-reads
