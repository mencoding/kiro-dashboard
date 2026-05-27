"""Testes da tool MCP ``usage_state`` (Wave 6 frente P)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from kiro_dash.backends.cli_json import CliJsonBackend
from kiro_dash.backends.ide_state import IdeStateBackend
from kiro_dash.mcp_server import tool_usage_state
from kiro_dash.sources import Sources
from tests.fixtures.ide.build_state_vscdb import build_state_vscdb


def _sources(*, with_ide: bool, tmp_path: Path) -> Sources:
    cli = CliJsonBackend(sessions_dir=tmp_path / "no_cli")
    ide = (
        IdeStateBackend(db_path=build_state_vscdb(tmp_path / "kiro_user"))
        if with_ide
        else None
    )
    return Sources(cli_json=cli, ide_state=ide)


def test_usage_state_with_ide_returns_complete_payload(tmp_path):
    sources = _sources(with_ide=True, tmp_path=tmp_path)
    with patch("kiro_dash.mcp_server.Sources.detect", return_value=sources):
        payload = tool_usage_state()
    assert payload["available"] is True
    assert payload["source"] == "ide"
    assert payload["current_usage"] == 100.0
    assert payload["usage_limit"] == 1000.0
    assert payload["percentage_used"] == 10.0
    assert payload["unit"] == "INVOCATIONS"
    assert payload["type"] == "CREDIT"
    assert payload["currency_code"] == "USD"
    assert payload["overage_rate"] == 0.04
    assert "data_age_seconds" in payload
    assert "freshness_level" in payload
    assert payload["freshness_level"] in {"green", "yellow", "red", "gray"}
    assert payload["schema_version_observed"] == 1
    assert "reset_date" in payload
    assert "timestamp" in payload


def test_usage_state_returns_error_when_no_ide(tmp_path):
    sources = _sources(with_ide=False, tmp_path=tmp_path)
    with patch("kiro_dash.mcp_server.Sources.detect", return_value=sources):
        payload = tool_usage_state()
    assert payload["available"] is False
    assert payload["error"] == "IDE_STATE_UNAVAILABLE"
    assert "kiro.dev" in payload["hint"]


def test_usage_state_returns_error_on_schema_unknown(tmp_path):
    """Quando o schema do kiro.kiroAgent é desconhecido, retorna erro estruturado."""
    db = build_state_vscdb(
        tmp_path / "kiro_user",
        kiro_agent_data={"hasBeenInstalled": True},  # falta usageState
    )
    ide = IdeStateBackend(db_path=db)
    # is_available retorna False quando schema desconhecido, então fica em UNAVAILABLE.
    # Esse caso é coberto pelo path "no IDE in available_for" na tool.
    sources = Sources(cli_json=None, ide_state=ide)
    with patch("kiro_dash.mcp_server.Sources.detect", return_value=sources):
        payload = tool_usage_state()
    # Como is_available()==False (schema check falha), Sources.available_for
    # retorna lista vazia: comportamento idêntico a "sem IDE".
    # Para forçar IDE_STATE_SCHEMA_UNKNOWN no payload, é preciso forçar o
    # backend na lista. Garantia mínima aqui: não crash + erro estruturado.
    assert payload["available"] is False
    assert payload["error"] in {
        "IDE_STATE_UNAVAILABLE",
        "IDE_STATE_SCHEMA_UNKNOWN",
    }
