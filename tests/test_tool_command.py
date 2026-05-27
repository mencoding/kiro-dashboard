"""Subcomando ``kiro-dash tool <name>``."""
from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from kiro_dash.cli import main
from kiro_dash.jsonl_parser import ToolCall


def _fake_tool_calls():
    return [
        ToolCall(name="shell", tool_use_id="t1", status="success",
                 session_id="s1", input_keys=["command"]),
        ToolCall(name="shell", tool_use_id="t2", status="error",
                 session_id="s1", input_keys=["command"],
                 error_summary="exit 1: command not found"),
        ToolCall(name="shell", tool_use_id="t3", status="error",
                 session_id="s2", input_keys=["command", "working_dir"],
                 error_summary="permission denied"),
        ToolCall(name="read", tool_use_id="t4", status="success",
                 session_id="s2", input_keys=["path"]),
    ]


def test_tool_command_filtra_pelo_nome():
    with patch("kiro_dash.cli.collect_recent_tools", return_value=_fake_tool_calls()):
        result = CliRunner().invoke(main, ["tool", "shell"])
    assert result.exit_code == 0
    assert "shell" in result.output
    assert "exit 1" in result.output
    assert "permission denied" in result.output


def test_tool_command_errors_only_filtra_status():
    with patch("kiro_dash.cli.collect_recent_tools", return_value=_fake_tool_calls()):
        result = CliRunner().invoke(main, ["tool", "shell", "--errors-only"])
    assert result.exit_code == 0
    assert "exit 1" in result.output
    assert "permission denied" in result.output
    # success t1 não deve aparecer
    assert "t1" not in result.output


def test_tool_command_sem_match_avisa():
    with patch("kiro_dash.cli.collect_recent_tools", return_value=_fake_tool_calls()):
        result = CliRunner().invoke(main, ["tool", "inexistente"])
    assert result.exit_code == 0
    assert "nenhuma" in result.output.lower()


def test_tool_command_show_input_lista_keys():
    with patch("kiro_dash.cli.collect_recent_tools", return_value=_fake_tool_calls()):
        result = CliRunner().invoke(main, ["tool", "shell"])
    assert "command" in result.output


def test_tool_command_tail_limit():
    with patch("kiro_dash.cli.collect_recent_tools", return_value=_fake_tool_calls()):
        result = CliRunner().invoke(main, ["tool", "shell", "--tail", "1"])
    assert result.exit_code == 0
