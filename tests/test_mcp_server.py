"""Testes das funções de tool do servidor MCP — sem subir o stdio."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from kiro_dash.mcp_server import (
    tool_account_info,
    tool_active_sessions,
    tool_session_details,
    tool_today_summary,
    tool_top_models,
    tool_top_projects,
)
from tests.fixtures.sessions_synthetic import make_session, make_turn


def _fake_sessions():
    """Fixture totalmente determinística — usa FAKE_NOW como referência."""
    return [
        make_session(
            session_id="aaaa1111-1111-1111-1111-111111111111",
            cwd="/proj/alfa",
            model_id="claude-opus-4.7",
            is_active=True,
            updated_at=FAKE_NOW - timedelta(minutes=1),
            turns=[
                make_turn(end_timestamp=FAKE_NOW - timedelta(minutes=5), credits=3.0),
                make_turn(end_timestamp=FAKE_NOW - timedelta(minutes=1), credits=2.0),
            ],
        ),
        make_session(
            session_id="bbbb2222-2222-2222-2222-222222222222",
            cwd="/proj/beta",
            model_id="auto",
            is_active=False,
            updated_at=FAKE_NOW - timedelta(minutes=20),
            turns=[make_turn(end_timestamp=FAKE_NOW - timedelta(minutes=20), credits=1.5)],
        ),
    ]


# Constante determinística — meio-dia local (UTC-3 → 15:00 UTC)
FAKE_NOW = datetime(2026, 5, 16, 15, 0, tzinfo=timezone.utc)


def test_today_summary_aggregates_local_day():
    with patch("kiro_dash.parser.load_all_sessions", return_value=_fake_sessions()):
        out = tool_today_summary(now=FAKE_NOW)
    assert out["total_credits"] == 6.5
    assert out["total_turns"] == 3
    assert out["total_sessions"] == 2
    assert {"by_model", "by_agent", "by_cwd"} <= set(out.keys())


def test_active_sessions_returns_only_locked():
    with patch("kiro_dash.parser.load_all_sessions", return_value=_fake_sessions()):
        out = tool_active_sessions()
    assert isinstance(out, list)
    assert len(out) == 1
    assert out[0]["session_id"].startswith("aaaa")
    assert out[0]["model_id"] == "claude-opus-4.7"


def test_session_details_by_prefix():
    fake = _fake_sessions()
    with patch("kiro_dash.mcp_server.find_session_by_prefix") as fp, \
         patch("kiro_dash.mcp_server.load_session_file", return_value=fake[0]):
        from pathlib import Path
        fp.return_value = Path("/tmp/aaaa.json")
        out = tool_session_details("aaaa")
    assert out is not None
    assert out["session_id"].startswith("aaaa")
    assert out["total_credits"] == 5.0
    assert out["turns_count"] == 2


def test_session_details_unknown_prefix():
    with patch("kiro_dash.mcp_server.find_session_by_prefix", return_value=None):
        out = tool_session_details("zzzz")
    assert out is None


def test_top_projects():
    with patch("kiro_dash.parser.load_all_sessions", return_value=_fake_sessions()):
        out = tool_top_projects(days=7, limit=10, now=FAKE_NOW)
    assert isinstance(out, list)
    cwds = {a["label"] for a in out}
    assert "/proj/alfa" in cwds
    assert "/proj/beta" in cwds


def test_top_models():
    with patch("kiro_dash.parser.load_all_sessions", return_value=_fake_sessions()):
        out = tool_top_models(days=7, limit=10, now=FAKE_NOW)
    labels = {a["label"] for a in out}
    assert "claude-opus-4.7" in labels


def test_account_info_when_kiro_cli_unavailable():
    with patch("kiro_dash.mcp_server.run_whoami", return_value=None):
        out = tool_account_info()
    assert out == {"available": False}


def test_account_info_returns_structured_when_available():
    from kiro_dash.account import WhoAmI
    fake = WhoAmI(
        account_type="IamIdentityCenter",
        email="x@y",
        region="sa-east-1",
        start_url=None,
        profile_name="P",
        profile_arn="arn:aws:codewhisperer:us-east-1:123456789012:profile/AB",
    )
    with patch("kiro_dash.mcp_server.run_whoami", return_value=fake):
        out = tool_account_info()
    assert out["available"] is True
    assert out["account_type"] == "IamIdentityCenter"
    assert out["aws_account_id"] == "123456789012"
    assert out["is_enterprise"] is True
