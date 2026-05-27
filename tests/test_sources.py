"""Testes do detector ``Sources`` (ADR-0001)."""
from __future__ import annotations

from pathlib import Path

from kiro_dash.backends import Backend, Capability
from kiro_dash.backends.cli_json import CliJsonBackend
from kiro_dash.backends.ide_state import IdeStateBackend
from kiro_dash.sources import Sources
from tests.fixtures.ide.build_state_vscdb import build_state_vscdb


def _make_cli_backend(tmp_path: Path, exists: bool = True) -> CliJsonBackend:
    sessions_dir = tmp_path / "kiro" / "sessions" / "cli"
    if exists:
        sessions_dir.mkdir(parents=True)
    return CliJsonBackend(sessions_dir=sessions_dir)


def _make_ide_backend(tmp_path: Path, exists: bool = True) -> IdeStateBackend:
    if exists:
        db = build_state_vscdb(tmp_path / "kiro_user")
        return IdeStateBackend(db_path=db)
    return IdeStateBackend(db_path=tmp_path / "missing.vscdb")


def test_sources_detect_with_both(tmp_path):
    cli = _make_cli_backend(tmp_path, exists=True)
    ide = _make_ide_backend(tmp_path, exists=True)
    s = Sources.detect(cli_json=cli, ide_state=ide)

    assert s.cli_json is cli
    assert s.ide_state is ide
    assert s.has_any() is True
    assert s.has_only_cli() is False


def test_sources_detect_cli_only(tmp_path):
    cli = _make_cli_backend(tmp_path, exists=True)
    s = Sources.detect(cli_json=cli, ide_state=None, ide_sessions=None)
    assert s.cli_json is cli
    assert s.ide_state is None
    assert s.has_any() is True
    assert s.has_only_cli() is True


def test_sources_detect_ide_only(tmp_path):
    ide = _make_ide_backend(tmp_path, exists=True)
    s = Sources.detect(cli_json=None, ide_state=ide)
    assert s.cli_json is None
    assert s.ide_state is ide
    assert s.has_any() is True
    assert s.has_only_cli() is False


def test_sources_detect_none(tmp_path):
    s = Sources.detect(cli_json=None, ide_state=None, ide_sessions=None)
    assert s.cli_json is None
    assert s.ide_state is None
    assert s.has_any() is False
    assert s.has_only_cli() is False


def test_sources_detect_skips_unavailable_cli(tmp_path):
    """Quando ``cli_json=...`` mas dir não existe → backend instanciado mas filtrado."""
    # Forçar pasta inexistente: apontamos default para um tmp limpo via env não suportada,
    # então usamos passagem explícita
    cli = _make_cli_backend(tmp_path, exists=False)
    s = Sources.detect(cli_json=cli, ide_state=None, ide_sessions=None)
    # Via passagem explícita (cli_json=cli), respeitamos a instância sem filtrar.
    # Mas o detector default filtra via is_available — testado em outro teste.
    assert s.cli_json is cli  # respeitou explícito
    assert s.has_only_cli() is True


def test_sources_default_detect_filters_unavailable(monkeypatch, tmp_path):
    """Default detect (sem args) deve instanciar e filtrar via is_available()."""
    # Apontar paths default para locais inexistentes via monkeypatch
    fake_sessions = tmp_path / "no_sessions"
    fake_state = tmp_path / "no_state.vscdb"
    fake_ide_root = tmp_path / "no_ide_root"

    from kiro_dash.backends import cli_json as cli_mod
    from kiro_dash.backends import ide_sessions as ide_sess_mod
    from kiro_dash.backends import ide_state as ide_mod

    monkeypatch.setattr(cli_mod, "DEFAULT_SESSIONS_DIR", fake_sessions)
    monkeypatch.setattr(ide_mod, "DEFAULT_IDE_STATE_VSCDB", fake_state)
    monkeypatch.setattr(ide_sess_mod, "DEFAULT_IDE_SESSIONS_ROOT", fake_ide_root)
    monkeypatch.delenv("KIRO_DASH_IDE_SESSIONS_ROOT", raising=False)

    s = Sources.detect()
    assert s.cli_json is None
    assert s.ide_state is None
    assert s.ide_sessions is None
    assert s.has_any() is False


def test_available_for_usage_state_prefers_ide(tmp_path):
    cli = _make_cli_backend(tmp_path, exists=True)
    ide = _make_ide_backend(tmp_path, exists=True)
    s = Sources.detect(cli_json=cli, ide_state=ide)
    backends = s.available_for(Capability.USAGE_STATE)
    assert backends == [ide]


def test_available_for_usage_state_empty_when_no_ide(tmp_path):
    cli = _make_cli_backend(tmp_path, exists=True)
    s = Sources.detect(cli_json=cli, ide_state=None)
    assert s.available_for(Capability.USAGE_STATE) == []


def test_available_for_sessions_uses_cli(tmp_path):
    cli = _make_cli_backend(tmp_path, exists=True)
    ide = _make_ide_backend(tmp_path, exists=True)
    s = Sources.detect(cli_json=cli, ide_state=ide)
    backends = s.available_for(Capability.SESSIONS)
    assert cli in backends
    # ide_state não fornece SESSIONS
    assert ide not in backends


def test_all_backends_only_returns_present(tmp_path):
    cli = _make_cli_backend(tmp_path, exists=True)
    s = Sources.detect(cli_json=cli, ide_state=None, ide_sessions=None)
    assert s.all_backends() == [cli]


def test_summary_lines_includes_all_slots(tmp_path):
    cli = _make_cli_backend(tmp_path, exists=True)
    ide = _make_ide_backend(tmp_path, exists=True)
    s = Sources.detect(cli_json=cli, ide_state=ide)
    lines = s.summary_lines()
    text = "\n".join(lines)
    assert "cli" in text
    assert "ide-state" in text
    assert "ide-sessions" in text
    assert "cli-sqlite" in text
    # Indicadores ✓ e —
    assert "✓" in text
    assert "—" in text


def test_summary_lines_marks_unavailable_with_dash(tmp_path):
    s = Sources.detect(cli_json=None, ide_state=None, ide_sessions=None)
    lines = s.summary_lines()
    text = "\n".join(lines)
    assert "✓" not in text
    assert text.count("—") >= 4


def test_summary_lines_shows_ide_sessions_count_when_present(tmp_path):
    """T10 — summary mostra contagem de workspaces no IDE Sessions."""
    from kiro_dash.backends.ide_sessions import IdeSessionBackend
    from tests.fixtures.ide.build_ide_layout import build_ide_layout

    kiro_root = build_ide_layout(tmp_path)
    backend = IdeSessionBackend(root=kiro_root)
    s = Sources.detect(cli_json=None, ide_state=None, ide_sessions=backend)
    text = "\n".join(s.summary_lines())
    assert "ide-sessions   ✓" in text
    assert "1 workspace" in text  # singular
    assert "atrás" in text  # idade do snapshot


def test_summary_lines_shows_ide_sessions_plural(tmp_path):
    """T10 — pluralização correta com 2+ workspaces."""
    from kiro_dash.backends.ide_sessions import IdeSessionBackend
    from tests.fixtures.ide.build_ide_layout import build_ide_layout

    kiro_root = build_ide_layout(
        tmp_path, extra_workspaces=["/home/test/another", "/srv/lab/xyz"]
    )
    backend = IdeSessionBackend(root=kiro_root)
    s = Sources.detect(cli_json=None, ide_state=None, ide_sessions=backend)
    text = "\n".join(s.summary_lines())
    assert "3 workspaces" in text  # plural


def test_available_for_sessions_includes_ide_sessions(tmp_path):
    """T10 — IdeSessionBackend aparece em available_for(SESSIONS)."""
    from kiro_dash.backends import Capability
    from kiro_dash.backends.ide_sessions import IdeSessionBackend
    from tests.fixtures.ide.build_ide_layout import build_ide_layout

    kiro_root = build_ide_layout(tmp_path)
    backend = IdeSessionBackend(root=kiro_root)
    s = Sources.detect(cli_json=None, ide_state=None, ide_sessions=backend)
    available = s.available_for(Capability.SESSIONS)
    assert backend in available
    available_running = s.available_for(Capability.RUNNING)
    assert backend in available_running
