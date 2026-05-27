"""Tests do skeleton IdeSessionBackend (T3 frente Q)."""
from __future__ import annotations

import os

import pytest

from kiro_dash.backends import Capability
from kiro_dash.backends.ide_sessions import (
    DEFAULT_IDE_SESSIONS_ROOT,
    ENV_DISABLE,
    ENV_OVERRIDE_ROOT,
    EXECUTIONS_CATALOG_FILENAME,
    IdeSessionBackend,
    Workspace,
)
from tests.fixtures.ide.build_ide_layout import (
    DEFAULT_PROFILE_HASH,
    DEFAULT_WORKSPACE_PATH,
    build_ide_layout,
)


def test_slug():
    backend = IdeSessionBackend(root=DEFAULT_IDE_SESSIONS_ROOT)
    assert backend.slug == "ide-sessions"


def test_capabilities():
    backend = IdeSessionBackend(root=DEFAULT_IDE_SESSIONS_ROOT)
    caps = backend.capabilities()
    assert caps == {
        Capability.SESSIONS,
        Capability.TURNS,
        Capability.TOOL_CALLS,
        Capability.RUNNING,
    }


def test_is_available_true_with_fixture(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    backend = IdeSessionBackend(root=kiro_root)
    assert backend.is_available() is True


def test_is_available_false_when_root_missing(tmp_path):
    backend = IdeSessionBackend(root=tmp_path / "does_not_exist")
    assert backend.is_available() is False


def test_is_available_false_without_workspace_sessions_dir(tmp_path):
    (tmp_path / "kiro.kiroagent").mkdir()
    backend = IdeSessionBackend(root=tmp_path / "kiro.kiroagent")
    assert backend.is_available() is False


def test_is_available_false_with_empty_workspace_sessions(tmp_path):
    kiro_root = tmp_path / "kiro.kiroagent"
    (kiro_root / "workspace-sessions").mkdir(parents=True)
    backend = IdeSessionBackend(root=kiro_root)
    assert backend.is_available() is False


def test_is_available_false_when_sessions_json_empty_list(tmp_path):
    kiro_root = tmp_path / "kiro.kiroagent"
    ws_dir = kiro_root / "workspace-sessions" / "L2hvbWUvdGVzdA__"
    ws_dir.mkdir(parents=True)
    (ws_dir / "sessions.json").write_text("[]")
    backend = IdeSessionBackend(root=kiro_root)
    assert backend.is_available() is False


def test_is_available_false_when_sessions_json_corrupt(tmp_path):
    kiro_root = tmp_path / "kiro.kiroagent"
    ws_dir = kiro_root / "workspace-sessions" / "L2hvbWUvdGVzdA__"
    ws_dir.mkdir(parents=True)
    (ws_dir / "sessions.json").write_text("{not json")
    backend = IdeSessionBackend(root=kiro_root)
    assert backend.is_available() is False


def test_is_available_disabled_by_env(tmp_path, monkeypatch):
    kiro_root = build_ide_layout(tmp_path)
    backend = IdeSessionBackend(root=kiro_root)
    assert backend.is_available() is True
    monkeypatch.setenv(ENV_DISABLE, "1")
    assert backend.is_available() is False


def test_default_root_uses_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv(ENV_OVERRIDE_ROOT, str(tmp_path / "custom_root"))
    backend = IdeSessionBackend()
    assert backend.root == tmp_path / "custom_root"


def test_default_root_without_env_uses_xdg_path(monkeypatch):
    monkeypatch.delenv(ENV_OVERRIDE_ROOT, raising=False)
    backend = IdeSessionBackend()
    assert "kiro.kiroagent" in str(backend.root)


def test_iter_workspaces_returns_one_for_default_fixture(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    backend = IdeSessionBackend(root=kiro_root)
    workspaces = backend.list_workspaces()
    assert len(workspaces) == 1
    ws = workspaces[0]
    assert isinstance(ws, Workspace)
    assert ws.path == DEFAULT_WORKSPACE_PATH
    assert ws.fs_dir.is_dir()
    assert (ws.fs_dir / "sessions.json").is_file()


def test_iter_workspaces_with_extra(tmp_path):
    extra = ["/home/test/another", "/srv/lab/xyz"]
    kiro_root = build_ide_layout(tmp_path, extra_workspaces=extra)
    backend = IdeSessionBackend(root=kiro_root)
    workspaces = backend.list_workspaces()
    paths = {ws.path for ws in workspaces}
    assert paths == {DEFAULT_WORKSPACE_PATH, *extra}


def test_iter_workspaces_skips_invalid_dir_names(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    # Plantar dir com nome inválido
    bad_dir = kiro_root / "workspace-sessions" / "this!is!not!base64"
    bad_dir.mkdir()
    (bad_dir / "sessions.json").write_text("[]")
    backend = IdeSessionBackend(root=kiro_root)
    workspaces = backend.list_workspaces()
    # Bad dir não aparece, default sim
    assert len(workspaces) == 1
    assert workspaces[0].path == DEFAULT_WORKSPACE_PATH


def test_iter_profile_hash_dirs(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    backend = IdeSessionBackend(root=kiro_root)
    profile_dirs = list(backend.iter_profile_hash_dirs())
    assert len(profile_dirs) == 1
    assert profile_dirs[0].name == DEFAULT_PROFILE_HASH
    assert (profile_dirs[0] / EXECUTIONS_CATALOG_FILENAME).is_file()


def test_iter_profile_hash_dirs_with_extra(tmp_path):
    extra_hashes = ["1111111111111111111111111111111b", "2222222222222222222222222222222c"]
    kiro_root = build_ide_layout(tmp_path, extra_profile_hashes=extra_hashes)
    backend = IdeSessionBackend(root=kiro_root)
    names = {d.name for d in backend.iter_profile_hash_dirs()}
    assert names == {DEFAULT_PROFILE_HASH, *extra_hashes}


def test_iter_profile_hash_dirs_ignores_default_and_workspace_sessions(tmp_path):
    """default/ symlink e workspace-sessions/ não devem ser confundidos com profiles."""
    kiro_root = build_ide_layout(tmp_path)
    backend = IdeSessionBackend(root=kiro_root)
    names = {d.name for d in backend.iter_profile_hash_dirs()}
    assert "default" not in names
    assert "workspace-sessions" not in names


def test_data_age_returns_seconds(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    backend = IdeSessionBackend(root=kiro_root)
    age = backend.data_age()
    assert age is not None
    assert age >= 0
    assert age < 60  # acabou de criar


def test_data_age_returns_none_when_no_workspace(tmp_path):
    kiro_root = tmp_path / "kiro.kiroagent"
    kiro_root.mkdir()
    backend = IdeSessionBackend(root=kiro_root)
    assert backend.data_age() is None
