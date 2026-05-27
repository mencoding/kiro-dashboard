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
        allowed = {"name", "tool_use_id", "status", "session_id", "input_keys", "error_summary"}
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


# ─── Wave 4: input_keys + error_summary ──────────────────────────────────


def test_tool_call_extrai_input_keys_sem_values(tmp_path):
    """toolUse.input vira lista de keys, sem values (privacidade)."""
    p = tmp_path / "x.jsonl"
    p.write_text(
        '{"version":"v1","kind":"AssistantMessage","data":{"content":[{"kind":"toolUse",'
        '"data":{"name":"shell","toolUseId":"abc","input":{"command":"rm -rf /","working_dir":"/tmp"}}}]}}\n'
    )
    calls = list(iter_tool_calls(p))
    assert len(calls) == 1
    assert calls[0].name == "shell"
    assert sorted(calls[0].input_keys) == ["command", "working_dir"]


def test_tool_call_input_keys_lista_vazia_quando_sem_input(tmp_path):
    p = tmp_path / "x.jsonl"
    p.write_text(
        '{"version":"v1","kind":"AssistantMessage","data":{"content":[{"kind":"toolUse",'
        '"data":{"name":"x","toolUseId":"abc","input":{}}}]}}\n'
    )
    calls = list(iter_tool_calls(p))
    assert calls[0].input_keys == []


def test_tool_call_error_summary_primeiros_200_chars(tmp_path):
    """toolResult.content vira error_summary só quando status=error."""
    p = tmp_path / "x.jsonl"
    long_err = "FileNotFoundError: [Errno 2] No such file or directory"
    p.write_text(
        '{"version":"v1","kind":"AssistantMessage","data":{"content":[{"kind":"toolUse",'
        '"data":{"name":"read","toolUseId":"abc","input":{"path":"/x"}}}]}}\n'
        '{"version":"v1","kind":"ToolResults","data":{"content":[{"kind":"toolResult",'
        '"data":{"toolUseId":"abc","content":"' + long_err + '","status":"error"}}]}}\n'
    )
    calls = list(iter_tool_calls(p))
    assert calls[0].error_summary is not None
    assert "FileNotFoundError" in calls[0].error_summary
    assert len(calls[0].error_summary) <= 200


def test_tool_call_error_summary_none_em_success(tmp_path):
    p = tmp_path / "x.jsonl"
    p.write_text(
        '{"version":"v1","kind":"AssistantMessage","data":{"content":[{"kind":"toolUse",'
        '"data":{"name":"read","toolUseId":"abc","input":{"path":"/x"}}}]}}\n'
        '{"version":"v1","kind":"ToolResults","data":{"content":[{"kind":"toolResult",'
        '"data":{"toolUseId":"abc","content":"file contents","status":"success"}}]}}\n'
    )
    calls = list(iter_tool_calls(p))
    assert calls[0].error_summary is None


def test_tool_call_error_summary_lista_chunks(tmp_path):
    """toolResult.content pode ser lista de chunks (cada chunk dict com text)."""
    p = tmp_path / "x.jsonl"
    p.write_text(
        '{"version":"v1","kind":"AssistantMessage","data":{"content":[{"kind":"toolUse",'
        '"data":{"name":"shell","toolUseId":"abc","input":{"command":"ls"}}}]}}\n'
        '{"version":"v1","kind":"ToolResults","data":{"content":[{"kind":"toolResult",'
        '"data":{"toolUseId":"abc","content":[{"kind":"text","data":"exit code 1"}],"status":"error"}}]}}\n'
    )
    calls = list(iter_tool_calls(p))
    assert calls[0].error_summary is not None
    assert "exit code 1" in calls[0].error_summary
