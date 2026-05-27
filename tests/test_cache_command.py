"""Testes dos subcomandos cache info/clear."""
from click.testing import CliRunner

from kiro_dash.cli import main


def test_cache_info_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    import kiro_dash.cache as cmod
    cmod._sessions_cache = None
    cmod._jsonl_cache = None

    runner = CliRunner()
    result = runner.invoke(main, ["cache", "info"])
    assert result.exit_code == 0
    assert "sessions" in result.output.lower()


def test_cache_clear_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    import kiro_dash.cache as cmod
    cmod._sessions_cache = None
    cmod._jsonl_cache = None

    runner = CliRunner()
    result = runner.invoke(main, ["cache", "clear"])
    assert result.exit_code == 0
    assert "limpo" in result.output.lower() or "removid" in result.output.lower()
