"""Tests T13 — MCP tools aceitam parâmetro source (frente Q)."""
from __future__ import annotations

from unittest.mock import patch

from kiro_dash.backends.ide_sessions import IdeSessionBackend
from kiro_dash.mcp_server import (
    tool_active_sessions,
    tool_session_details,
)
from kiro_dash.sources import Sources
from tests.fixtures.ide.build_ide_layout import (
    SESSION_ID,
    build_ide_layout,
)


def _ide_only_sources(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    return Sources(
        cli_json=None,
        ide_state=None,
        ide_sessions=IdeSessionBackend(root=kiro_root),
    )


# ── tool_active_sessions ─────────────────────────────────────────────


def test_active_sessions_default_cli():
    """Sem source param, default é cli."""
    with patch("kiro_dash.mcp_server.load_all_sessions", return_value=[]):
        result = tool_active_sessions()
    assert result == []


def test_active_sessions_ide_with_running(tmp_path):
    sources = _ide_only_sources(tmp_path)
    with patch("kiro_dash.mcp_server.load_all_sessions", return_value=[]), patch(
        "kiro_dash.mcp_server.Sources.detect", return_value=sources
    ):
        result = tool_active_sessions(source="ide")
    assert len(result) == 1
    assert result[0]["source"] == "ide"
    assert result[0]["session_id"] == f"ide-sessions:{SESSION_ID}"


def test_active_sessions_all_concatenates(tmp_path):
    sources = _ide_only_sources(tmp_path)
    with patch("kiro_dash.mcp_server.load_all_sessions", return_value=[]), patch(
        "kiro_dash.mcp_server.Sources.detect", return_value=sources
    ):
        result = tool_active_sessions(source="all")
    # 0 CLI + 1 IDE
    assert len(result) == 1
    assert result[0]["source"] == "ide"


def test_active_sessions_ide_no_running_when_excluded(tmp_path):
    kiro_root = build_ide_layout(tmp_path, include_running=False)
    sources = Sources(
        cli_json=None,
        ide_state=None,
        ide_sessions=IdeSessionBackend(root=kiro_root),
    )
    with patch("kiro_dash.mcp_server.load_all_sessions", return_value=[]), patch(
        "kiro_dash.mcp_server.Sources.detect", return_value=sources
    ):
        result = tool_active_sessions(source="ide")
    assert result == []


# ── tool_session_details ─────────────────────────────────────────────


def test_session_details_ide_explicit_source(tmp_path):
    sources = _ide_only_sources(tmp_path)
    with patch("kiro_dash.mcp_server.Sources.detect", return_value=sources):
        result = tool_session_details(SESSION_ID[:8], source="ide")
    assert result is not None
    assert result["source"] == "ide"
    assert result["session_id"] == f"ide-sessions:{SESSION_ID}"
    assert result["turns_count"] == 7


def test_session_details_auto_finds_in_ide(tmp_path):
    """source=auto resolve em IDE quando CLI não encontra."""
    sources = _ide_only_sources(tmp_path)
    with patch(
        "kiro_dash.mcp_server.find_session_by_prefix", return_value=None
    ), patch("kiro_dash.mcp_server.Sources.detect", return_value=sources):
        result = tool_session_details(SESSION_ID[:8])  # default source=auto
    assert result is not None
    assert result["source"] == "ide"


def test_session_details_returns_none_when_no_match():
    sources = Sources(cli_json=None, ide_state=None, ide_sessions=None)
    with patch(
        "kiro_dash.mcp_server.find_session_by_prefix", return_value=None
    ), patch("kiro_dash.mcp_server.Sources.detect", return_value=sources):
        result = tool_session_details("zzz")
    assert result is None


def test_session_details_ide_running_turn_serialized(tmp_path):
    """Turn com end_timestamp=None é serializado como null."""
    sources = _ide_only_sources(tmp_path)
    with patch("kiro_dash.mcp_server.Sources.detect", return_value=sources):
        result = tool_session_details(SESSION_ID[:8], source="ide")
    assert result is not None
    # Tem ao menos 1 turn com end_timestamp=None (running)
    has_running = any(t["end_timestamp"] is None for t in result["turns"])
    assert has_running


def test_session_details_ide_session_has_total_credits(tmp_path):
    sources = _ide_only_sources(tmp_path)
    with patch("kiro_dash.mcp_server.Sources.detect", return_value=sources):
        result = tool_session_details(SESSION_ID[:8], source="ide")
    assert result is not None
    assert result["total_credits"] > 1.5
    assert result["agent_name"] == "kiro-ide"


# ── _collect_sessions_for_mcp helper ─────────────────────────────────


def test_collect_sessions_for_mcp_invalid_source_falls_back_to_cli():
    """Source inválido cai para 'cli' silenciosamente."""
    from kiro_dash.mcp_server import _collect_sessions_for_mcp

    with patch("kiro_dash.mcp_server.load_all_sessions", return_value=[]):
        result = _collect_sessions_for_mcp("bogus")
    assert result == []


def test_collect_sessions_for_mcp_ide_only(tmp_path):
    from kiro_dash.mcp_server import _collect_sessions_for_mcp

    sources = _ide_only_sources(tmp_path)
    with patch("kiro_dash.mcp_server.Sources.detect", return_value=sources):
        result = _collect_sessions_for_mcp("ide")
    assert len(result) == 1
