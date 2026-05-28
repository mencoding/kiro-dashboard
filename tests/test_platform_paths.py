"""Tests T2-W10 — paths cross-platform.

Wave 10: cobertura para Linux, Windows e macOS via mock de
``sys.platform`` e env vars (APPDATA, LOCALAPPDATA, XDG_CONFIG_HOME,
XDG_DATA_HOME).
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from kiro_dash import _platform_paths as pp


# ── user_config_dir() ──────────────────────────────────────────────


def test_user_config_dir_linux_xdg(monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", "/custom/xdg")
    monkeypatch.setattr("sys.platform", "linux")
    assert pp.user_config_dir() == Path("/custom/xdg")


def test_user_config_dir_linux_default(monkeypatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr("sys.platform", "linux")
    assert pp.user_config_dir() == Path.home() / ".config"


def test_user_config_dir_windows_with_appdata(monkeypatch):
    monkeypatch.setenv("APPDATA", "C:/Users/test/AppData/Roaming")
    monkeypatch.setattr("sys.platform", "win32")
    assert pp.user_config_dir() == Path("C:/Users/test/AppData/Roaming")


def test_user_config_dir_windows_no_appdata(monkeypatch):
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setattr("sys.platform", "win32")
    expected = Path.home() / "AppData" / "Roaming"
    assert pp.user_config_dir() == expected


def test_user_config_dir_macos(monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    expected = Path.home() / "Library" / "Application Support"
    assert pp.user_config_dir() == expected


# ── user_data_dir() ────────────────────────────────────────────────


def test_user_data_dir_linux_xdg(monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", "/custom/xdg-data")
    monkeypatch.setattr("sys.platform", "linux")
    assert pp.user_data_dir() == Path("/custom/xdg-data")


def test_user_data_dir_linux_default(monkeypatch):
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setattr("sys.platform", "linux")
    assert pp.user_data_dir() == Path.home() / ".local" / "share"


def test_user_data_dir_windows_with_localappdata(monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", "C:/Users/test/AppData/Local")
    monkeypatch.setattr("sys.platform", "win32")
    assert pp.user_data_dir() == Path("C:/Users/test/AppData/Local")


def test_user_data_dir_windows_no_localappdata(monkeypatch):
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setattr("sys.platform", "win32")
    assert pp.user_data_dir() == Path.home() / "AppData" / "Local"


def test_user_data_dir_macos(monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    assert pp.user_data_dir() == Path.home() / "Library" / "Application Support"


# ── Kiro IDE paths ─────────────────────────────────────────────────


def test_kiro_ide_globalstorage_dir_linux(monkeypatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr("sys.platform", "linux")
    expected = Path.home() / ".config" / "Kiro" / "User" / "globalStorage"
    assert pp.kiro_ide_globalstorage_dir() == expected


def test_kiro_ide_globalstorage_dir_windows(monkeypatch):
    monkeypatch.setenv("APPDATA", "C:/Users/test/AppData/Roaming")
    monkeypatch.setattr("sys.platform", "win32")
    expected = Path("C:/Users/test/AppData/Roaming/Kiro/User/globalStorage")
    assert pp.kiro_ide_globalstorage_dir() == expected


def test_kiro_ide_state_db_path_linux(monkeypatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr("sys.platform", "linux")
    expected = Path.home() / ".config" / "Kiro" / "User" / "globalStorage" / "state.vscdb"
    assert pp.kiro_ide_state_db_path() == expected


def test_kiro_ide_state_db_path_windows(monkeypatch):
    monkeypatch.setenv("APPDATA", "C:/Users/test/AppData/Roaming")
    monkeypatch.setattr("sys.platform", "win32")
    expected = Path("C:/Users/test/AppData/Roaming/Kiro/User/globalStorage/state.vscdb")
    assert pp.kiro_ide_state_db_path() == expected


def test_kiro_ide_kiroagent_dir_linux(monkeypatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr("sys.platform", "linux")
    expected = (
        Path.home() / ".config" / "Kiro" / "User" / "globalStorage" / "kiro.kiroagent"
    )
    assert pp.kiro_ide_kiroagent_dir() == expected


def test_kiro_ide_kiroagent_dir_windows(monkeypatch):
    monkeypatch.setenv("APPDATA", "C:/Users/test/AppData/Roaming")
    monkeypatch.setattr("sys.platform", "win32")
    expected = Path("C:/Users/test/AppData/Roaming/Kiro/User/globalStorage/kiro.kiroagent")
    assert pp.kiro_ide_kiroagent_dir() == expected


# ── Kiro CLI paths (dotfile, não muda por OS) ──────────────────────


@pytest.mark.parametrize("platform", ["linux", "win32", "darwin"])
def test_kiro_cli_sessions_dir_same_across_os(platform, monkeypatch):
    monkeypatch.setattr("sys.platform", platform)
    expected = Path.home() / ".kiro" / "sessions" / "cli"
    assert pp.kiro_cli_sessions_dir() == expected


@pytest.mark.parametrize("platform", ["linux", "win32", "darwin"])
def test_kiro_cli_agents_dir_same_across_os(platform, monkeypatch):
    monkeypatch.setattr("sys.platform", platform)
    expected = Path.home() / ".kiro" / "agents"
    assert pp.kiro_cli_agents_dir() == expected


# ── kiro-dash own paths ────────────────────────────────────────────


def test_kiro_dash_config_dir_linux(monkeypatch):
    monkeypatch.delenv("KIRO_DASH_CONFIG_DIR", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr("sys.platform", "linux")
    expected = Path.home() / ".config" / "kiro-dash"
    assert pp.kiro_dash_config_dir() == expected


def test_kiro_dash_config_dir_windows(monkeypatch):
    monkeypatch.delenv("KIRO_DASH_CONFIG_DIR", raising=False)
    monkeypatch.setenv("APPDATA", "C:/Users/test/AppData/Roaming")
    monkeypatch.setattr("sys.platform", "win32")
    expected = Path("C:/Users/test/AppData/Roaming/kiro-dash")
    assert pp.kiro_dash_config_dir() == expected


def test_kiro_dash_config_dir_env_override(monkeypatch):
    monkeypatch.setenv("KIRO_DASH_CONFIG_DIR", "/tmp/custom-config")
    expected = Path("/tmp/custom-config")
    assert pp.kiro_dash_config_dir() == expected


def test_kiro_dash_data_dir_linux(monkeypatch):
    monkeypatch.delenv("KIRO_DASH_DATA_DIR", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setattr("sys.platform", "linux")
    expected = Path.home() / ".local" / "share" / "kiro-dash"
    assert pp.kiro_dash_data_dir() == expected


def test_kiro_dash_data_dir_windows(monkeypatch):
    monkeypatch.delenv("KIRO_DASH_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", "C:/Users/test/AppData/Local")
    monkeypatch.setattr("sys.platform", "win32")
    expected = Path("C:/Users/test/AppData/Local/kiro-dash")
    assert pp.kiro_dash_data_dir() == expected


def test_kiro_dash_data_dir_macos(monkeypatch):
    monkeypatch.delenv("KIRO_DASH_DATA_DIR", raising=False)
    monkeypatch.setattr("sys.platform", "darwin")
    expected = Path.home() / "Library" / "Application Support" / "kiro-dash"
    assert pp.kiro_dash_data_dir() == expected


def test_kiro_dash_data_dir_env_override(monkeypatch):
    monkeypatch.setenv("KIRO_DASH_DATA_DIR", "/tmp/custom-data")
    expected = Path("/tmp/custom-data")
    assert pp.kiro_dash_data_dir() == expected


# ── Sanity ─────────────────────────────────────────────────────────


def test_all_helpers_return_path_objects():
    """Garante que nenhum helper retorna string."""
    assert isinstance(pp.user_config_dir(), Path)
    assert isinstance(pp.user_data_dir(), Path)
    assert isinstance(pp.kiro_ide_globalstorage_dir(), Path)
    assert isinstance(pp.kiro_ide_state_db_path(), Path)
    assert isinstance(pp.kiro_ide_kiroagent_dir(), Path)
    assert isinstance(pp.kiro_ide_workspacestorage_dir(), Path)
    assert isinstance(pp.kiro_cli_sessions_dir(), Path)
    assert isinstance(pp.kiro_cli_agents_dir(), Path)
    assert isinstance(pp.kiro_dash_config_dir(), Path)
    assert isinstance(pp.kiro_dash_data_dir(), Path)


def test_paths_diverge_between_linux_and_windows(monkeypatch):
    """IDE paths devem ser diferentes entre Linux e Windows."""
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    linux_path = pp.kiro_ide_globalstorage_dir()

    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("APPDATA", "C:/AppData")
    windows_path = pp.kiro_ide_globalstorage_dir()

    assert linux_path != windows_path
    assert ".config" in str(linux_path)
    assert "AppData" in str(windows_path)
