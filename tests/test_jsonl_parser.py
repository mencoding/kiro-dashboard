"""Testes do parser de transcript .jsonl — cego ao conteúdo."""
from __future__ import annotations

from pathlib import Path

from kiro_dash.jsonl_parser import ToolCall, iter_tool_calls

FIXTURE = Path(__file__).parent / "fixtures" / "sample_session.jsonl"


def test_iter_tool_calls_extracts_only_tool_use_events():
    calls = list(iter_tool_calls(FIXTURE))
    assert len(calls) == 3
    names = [c.name for c in calls]
    assert names == ["read", "glob", "read"]


def test_iter_tool_calls_correlates_status_from_tool_results():
    calls = list(iter_tool_calls(FIXTURE))
    by_id = {c.tool_use_id: c.status for c in calls}
    assert by_id == {
        "tu_001": "success",
        "tu_002": "success",
        "tu_003": "error",
    }


def test_iter_tool_calls_does_not_expose_text_or_thinking():
    """Garante que NENHUM campo do retorno carrega conteúdo de mensagens."""
    calls = list(iter_tool_calls(FIXTURE))
    for c in calls:
        allowed = {"name", "tool_use_id", "status", "session_id"}
        assert set(c.__dataclass_fields__.keys()) == allowed


def test_iter_tool_calls_missing_file_returns_empty():
    calls = list(iter_tool_calls(Path("/tmp/nonexistent.jsonl")))
    assert calls == []


def test_iter_tool_calls_malformed_lines_skipped(tmp_path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text(
        '{"kind":"Prompt"}\n'
        'not-json\n'
        '{"kind":"AssistantMessage","data":{"content":[{"kind":"toolUse","data":{"name":"read","toolUseId":"x"}}]}}\n'
    )
    calls = list(iter_tool_calls(bad))
    assert len(calls) == 1
    assert calls[0].name == "read"
