"""Cobertura do cache layer com mtime invalidation."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from kiro_dash.cache import SessionsCache, cache_dir_default, clear_cache, cache_info


@pytest.fixture
def cache(tmp_path):
    return SessionsCache(root=tmp_path / "cache")


@pytest.fixture
def src_file(tmp_path):
    p = tmp_path / "session.json"
    p.write_text(json.dumps({"k": "v"}))
    return p


def test_get_returns_none_when_empty(cache, src_file):
    assert cache.get(src_file) is None


def test_put_then_get_hits(cache, src_file):
    cache.put(src_file, {"data": [1, 2, 3]})
    assert cache.get(src_file) == {"data": [1, 2, 3]}


def test_get_misses_after_mtime_change(cache, src_file):
    cache.put(src_file, {"data": "old"})
    time.sleep(0.01)
    src_file.write_text(json.dumps({"k": "v2"}))
    assert cache.get(src_file) is None


def test_get_misses_after_size_change(cache, src_file):
    cache.put(src_file, {"data": "old"})
    mtime = src_file.stat().st_mtime
    src_file.write_text(json.dumps({"k": "v" * 100}))
    os.utime(src_file, (mtime, mtime))
    assert cache.get(src_file) is None


def test_get_returns_none_when_source_deleted(cache, src_file):
    cache.put(src_file, {"data": "x"})
    src_file.unlink()
    assert cache.get(src_file) is None


def test_clear_removes_all(cache, src_file):
    cache.put(src_file, {"data": "x"})
    cache.clear()
    assert cache.get(src_file) is None


def test_info_reports_count_and_size(cache, src_file, tmp_path):
    other = tmp_path / "other.json"
    other.write_text("{}")
    cache.put(src_file, {"a": 1})
    cache.put(other, {"b": 2})
    info = cache.info()
    assert info["entries"] == 2
    assert info["bytes"] > 0


def test_no_cache_env_disables(cache, src_file, monkeypatch):
    monkeypatch.setenv("KIRO_DASH_NO_CACHE", "1")
    cache.put(src_file, {"x": 1})
    assert cache.get(src_file) is None


def test_cache_dir_default_uses_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert cache_dir_default() == tmp_path / "kiro-dash"
