"""Tests T11 — flag --source nos comandos CLI (frente Q)."""
from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from kiro_dash.backends.ide_sessions import IdeSessionBackend
from kiro_dash.cli import (
    _collect_sessions_by_source,
    _find_session_by_prefix_in_ide,
    audit_running,
    main,
    recent,
    session,
)
from kiro_dash.sources import Sources
from tests.fixtures.ide.build_ide_layout import (
    SESSION_ID,
    build_ide_layout,
)


def _ide_only_sources(tmp_path):
    """Sources com apenas IDE backend."""
    kiro_root = build_ide_layout(tmp_path)
    return Sources(
        cli_json=None,
        ide_state=None,
        ide_sessions=IdeSessionBackend(root=kiro_root),
    )


# ── helper unitário ──────────────────────────────────────────────────


def test_collect_sessions_cli_source(tmp_path):
    """source=cli usa load_all_sessions."""
    with patch("kiro_dash.cli.load_all_sessions", return_value=[]):
        result = _collect_sessions_by_source("cli")
    assert result == []


def test_collect_sessions_ide_source(tmp_path):
    """source=ide usa Sources.detect.ide_sessions.list_sessions."""
    sources = _ide_only_sources(tmp_path)
    result = _collect_sessions_by_source("ide", sources=sources)
    assert len(result) == 1
    assert result[0].session_id.startswith("ide-sessions:")


def test_collect_sessions_all_concatenates(tmp_path):
    """source=all concatena CLI + IDE."""
    sources = _ide_only_sources(tmp_path)
    with patch("kiro_dash.cli.load_all_sessions", return_value=[]):
        result = _collect_sessions_by_source("all", sources=sources)
    # 0 CLI + 1 IDE
    assert len(result) == 1


def test_find_session_by_prefix_in_ide_match(tmp_path):
    sources = _ide_only_sources(tmp_path)
    s = _find_session_by_prefix_in_ide(SESSION_ID[:8], sources=sources)
    assert s is not None
    assert s.session_id == f"ide-sessions:{SESSION_ID}"


def test_find_session_by_prefix_in_ide_no_match(tmp_path):
    sources = _ide_only_sources(tmp_path)
    s = _find_session_by_prefix_in_ide("zzzzzzzz", sources=sources)
    assert s is None


def test_find_session_by_prefix_in_ide_no_backend(tmp_path):
    sources = Sources(cli_json=None, ide_state=None, ide_sessions=None)
    s = _find_session_by_prefix_in_ide("anything", sources=sources)
    assert s is None


# ── recent CLI ───────────────────────────────────────────────────────


def test_recent_cli_default_works():
    """recent --source cli mantém comportamento original."""
    runner = CliRunner()
    with patch("kiro_dash.cli.load_all_sessions", return_value=[]):
        result = runner.invoke(main, ["recent"])
    assert result.exit_code == 0
    assert "Nenhuma sessão" in result.output


def test_recent_ide_lists_ide_sessions(tmp_path):
    """recent --source ide retorna sessão IDE da fixture."""
    sources = _ide_only_sources(tmp_path)
    runner = CliRunner()
    with patch("kiro_dash.cli.load_all_sessions", return_value=[]), patch(
        "kiro_dash.cli.Sources.detect", return_value=sources
    ):
        result = runner.invoke(main, ["recent", "--source", "ide"])
    assert result.exit_code == 0, result.output
    # Verifica que mostra a sessão IDE
    assert SESSION_ID[:8] in result.output


def test_recent_all_concatenates(tmp_path):
    """recent --source all concatena CLI + IDE com coluna source."""
    sources = _ide_only_sources(tmp_path)
    runner = CliRunner()
    with patch("kiro_dash.cli.load_all_sessions", return_value=[]), patch(
        "kiro_dash.cli.Sources.detect", return_value=sources
    ):
        result = runner.invoke(main, ["recent", "--source", "all"])
    assert result.exit_code == 0, result.output
    # Coluna source aparece em modo all
    assert "source" in result.output.lower()


def test_recent_show_source_flag(tmp_path):
    """--show-source força coluna source mesmo em --source ide."""
    sources = _ide_only_sources(tmp_path)
    runner = CliRunner()
    with patch("kiro_dash.cli.load_all_sessions", return_value=[]), patch(
        "kiro_dash.cli.Sources.detect", return_value=sources
    ):
        result = runner.invoke(
            main, ["recent", "--source", "ide", "--show-source"]
        )
    assert result.exit_code == 0
    assert "ide" in result.output


# ── audit running CLI ────────────────────────────────────────────────


def test_audit_running_ide_finds_running_execution(tmp_path):
    """audit running --source ide detecta execution status=running."""
    sources = _ide_only_sources(tmp_path)
    runner = CliRunner()
    with patch("kiro_dash.cli.load_all_sessions", return_value=[]), patch(
        "kiro_dash.cli.Sources.detect", return_value=sources
    ):
        result = runner.invoke(main, ["audit", "running", "--source", "ide"])
    assert result.exit_code == 0, result.output
    # Tem 1 execution running na fixture default
    assert SESSION_ID[:8] in result.output


def test_audit_running_no_running_when_excluded(tmp_path):
    """audit running --source ide sem running execution → 'Nenhuma'."""
    kiro_root = build_ide_layout(tmp_path, include_running=False)
    sources = Sources(
        cli_json=None,
        ide_state=None,
        ide_sessions=IdeSessionBackend(root=kiro_root),
    )
    runner = CliRunner()
    with patch("kiro_dash.cli.load_all_sessions", return_value=[]), patch(
        "kiro_dash.cli.Sources.detect", return_value=sources
    ):
        result = runner.invoke(main, ["audit", "running", "--source", "ide"])
    assert result.exit_code == 0
    assert "Nenhuma" in result.output or "nenhuma" in result.output.lower()


def test_audit_running_all_includes_source_column(tmp_path):
    """audit running --source all mostra coluna source."""
    sources = _ide_only_sources(tmp_path)
    runner = CliRunner()
    with patch("kiro_dash.cli.load_all_sessions", return_value=[]), patch(
        "kiro_dash.cli.Sources.detect", return_value=sources
    ):
        result = runner.invoke(main, ["audit", "running", "--source", "all"])
    assert result.exit_code == 0
    assert "source" in result.output.lower()


# ── session prefix resolution ────────────────────────────────────────


def test_session_resolves_in_ide_when_only_ide_match(tmp_path):
    """session <prefix> com auto resolve para IDE quando só IDE casa."""
    sources = _ide_only_sources(tmp_path)
    runner = CliRunner()
    with patch(
        "kiro_dash.cli.find_session_by_prefix", return_value=None
    ), patch("kiro_dash.cli.Sources.detect", return_value=sources):
        result = runner.invoke(main, ["session", SESSION_ID[:8]])
    assert result.exit_code == 0, result.output
    assert SESSION_ID[:8] in result.output
    # Sessão IDE: tem 7 turns
    assert "7 turns" in result.output


def test_session_explicit_ide_source(tmp_path):
    """session --source ide força backend IDE."""
    sources = _ide_only_sources(tmp_path)
    runner = CliRunner()
    with patch("kiro_dash.cli.Sources.detect", return_value=sources):
        result = runner.invoke(main, ["session", "--source", "ide", SESSION_ID[:8]])
    assert result.exit_code == 0
    assert SESSION_ID[:8] in result.output


def test_session_running_turn_renders_without_crash(tmp_path):
    """Turn com end_timestamp=None (running) não quebra renderização."""
    sources = _ide_only_sources(tmp_path)
    runner = CliRunner()
    with patch("kiro_dash.cli.Sources.detect", return_value=sources):
        result = runner.invoke(main, ["session", "--source", "ide", SESSION_ID[:8]])
    assert result.exit_code == 0, result.output
    # Pelo menos um turn é "running" na fixture default (EXEC_RUNNING)
    assert "running" in result.output.lower()


def test_session_not_found_in_either_source():
    """session com prefix que não casa em nada → erro."""
    sources = Sources(cli_json=None, ide_state=None, ide_sessions=None)
    runner = CliRunner()
    with patch(
        "kiro_dash.cli.find_session_by_prefix", return_value=None
    ), patch("kiro_dash.cli.Sources.detect", return_value=sources):
        result = runner.invoke(main, ["session", "nope-uuid"])
    assert result.exit_code == 1
    assert "não encontrada" in result.output or "ambíguo" in result.output
