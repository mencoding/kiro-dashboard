"""Paths cross-platform para storage do Kiro IDE/CLI e do próprio kiro-dash.

Wave 10 (v0.8.0): suporte explícito a Windows 11, macOS e Linux.

Mapeamento por OS:

| Recurso            | Linux                   | Windows               | macOS                                |
|--------------------|-------------------------|-----------------------|--------------------------------------|
| User data (config) | ``$XDG_CONFIG_HOME``    | ``%APPDATA%``         | ``~/Library/Application Support``    |
|                    | ou ``~/.config``        | (Roaming)             |                                      |
| User local data    | ``$XDG_DATA_HOME`` ou   | ``%LOCALAPPDATA%``    | ``~/Library/Application Support``    |
|                    | ``~/.local/share``      | (Local)               |                                      |
| Kiro IDE storage   | ``~/.config/Kiro/...``  | ``%APPDATA%/Kiro/...``| ``~/Library/.../Kiro/...``           |
| kiro-cli sessions  | ``~/.kiro/sessions/...``| idem (dotfile dir)    | idem                                 |

Convenções:

- ``~/.kiro/`` (kiro-cli) usa dotfile home cross-platform — não muda.
- ``Kiro/User/globalStorage/`` (Kiro IDE) segue convenção VSCode-like
  e diverge por OS: Roaming em Win, XDG em Linux, Application Support
  em macOS.

Env vars de override (precedência sobre default):

- ``KIRO_DASH_IDE_SESSIONS_ROOT`` — sobrescreve raiz IDE sessions.
- ``KIRO_DASH_CONFIG_DIR`` — sobrescreve config dir do próprio dash.
- ``KIRO_DASH_DATA_DIR`` — sobrescreve data dir (snapshots).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _is_windows() -> bool:
    return sys.platform == "win32"


def _is_macos() -> bool:
    return sys.platform == "darwin"


# ── Diretórios genéricos por convenção do OS ────────────────────────


def user_config_dir() -> Path:
    """Diretório de config do usuário, app-agnóstico.

    - Linux: ``$XDG_CONFIG_HOME`` ou ``~/.config``
    - Windows: ``%APPDATA%`` (Roaming) ou ``~/AppData/Roaming``
    - macOS: ``~/Library/Application Support``
    """
    if _is_windows():
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata)
        return Path.home() / "AppData" / "Roaming"
    if _is_macos():
        return Path.home() / "Library" / "Application Support"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)
    return Path.home() / ".config"


def user_data_dir() -> Path:
    """Diretório de dados locais do usuário (snapshots, caches grandes).

    - Linux: ``$XDG_DATA_HOME`` ou ``~/.local/share``
    - Windows: ``%LOCALAPPDATA%`` (Local — não-Roaming) ou ``~/AppData/Local``
    - macOS: ``~/Library/Application Support`` (mesmo que config — convenção)
    """
    if _is_windows():
        local = os.environ.get("LOCALAPPDATA")
        if local:
            return Path(local)
        return Path.home() / "AppData" / "Local"
    if _is_macos():
        return Path.home() / "Library" / "Application Support"
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg)
    return Path.home() / ".local" / "share"


# ── Paths específicos do Kiro IDE ──────────────────────────────────


def kiro_ide_globalstorage_dir() -> Path:
    """``<user_config>/Kiro/User/globalStorage``.

    Aqui ficam ``state.vscdb`` e ``kiro.kiroagent/``.
    """
    return user_config_dir() / "Kiro" / "User" / "globalStorage"


def kiro_ide_workspacestorage_dir() -> Path:
    """``<user_config>/Kiro/User/workspaceStorage``."""
    return user_config_dir() / "Kiro" / "User" / "workspaceStorage"


def kiro_ide_state_db_path() -> Path:
    """``<global_storage>/state.vscdb`` (DB SQLite do Kiro IDE)."""
    return kiro_ide_globalstorage_dir() / "state.vscdb"


def kiro_ide_kiroagent_dir() -> Path:
    """``<global_storage>/kiro.kiroagent`` — sessões e executions IDE."""
    return kiro_ide_globalstorage_dir() / "kiro.kiroagent"


# ── Paths específicos do kiro-cli ──────────────────────────────────


def kiro_cli_dotfile_dir() -> Path:
    """``~/.kiro`` — convenção dotfiles cross-platform.

    O kiro-cli (Amazon Q rebrand) escreve em ``~/.kiro/`` em todos os
    OSes que tem instalador oficial; não muda por plataforma.
    """
    return Path.home() / ".kiro"


def kiro_cli_sessions_dir() -> Path:
    """``~/.kiro/sessions/cli`` — JSONs de sessões do CLI."""
    return kiro_cli_dotfile_dir() / "sessions" / "cli"


def kiro_cli_agents_dir() -> Path:
    """``~/.kiro/agents`` — JSONs de configuração de agents."""
    return kiro_cli_dotfile_dir() / "agents"


# ── Paths do próprio kiro-dash ─────────────────────────────────────


def kiro_dash_config_dir() -> Path:
    """``<user_config>/kiro-dash`` ou env ``KIRO_DASH_CONFIG_DIR``."""
    env = os.environ.get("KIRO_DASH_CONFIG_DIR")
    if env:
        return Path(env).expanduser()
    return user_config_dir() / "kiro-dash"


def kiro_dash_data_dir() -> Path:
    """``<user_data>/kiro-dash`` ou env ``KIRO_DASH_DATA_DIR``.

    Aqui ficam snapshots persistidos.
    """
    env = os.environ.get("KIRO_DASH_DATA_DIR")
    if env:
        return Path(env).expanduser()
    return user_data_dir() / "kiro-dash"
