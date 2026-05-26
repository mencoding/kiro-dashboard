"""Smoke do subcomando tools."""
from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from kiro_dash.cli import main


def test_tools_renders_table_when_data_available(tmp_path):
    j = tmp_path / "11111111.jsonl"
    j.write_text(
        '{"version":"v1","kind":"AssistantMessage","data":{"content":['
        '{"kind":"toolUse","data":{"name":"read","toolUseId":"a"}},'
        '{"kind":"toolUse","data":{"name":"shell","toolUseId":"b"}},'
        '{"kind":"toolUse","data":{"name":"read","toolUseId":"c"}}'
        ']}}\n'
    )
    with patch("kiro_dash.cli.DEFAULT_SESSIONS_DIR", tmp_path):
        runner = CliRunner()
        result = runner.invoke(main, ["tools", "--hours", "48"])
    assert result.exit_code == 0
    assert "read" in result.output
    assert "shell" in result.output


def test_tools_empty_window_shows_message(tmp_path):
    with patch("kiro_dash.cli.DEFAULT_SESSIONS_DIR", tmp_path):
        runner = CliRunner()
        result = runner.invoke(main, ["tools"])
    assert result.exit_code == 0
    assert "Nenhuma" in result.output or "Sem" in result.output
