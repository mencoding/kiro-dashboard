"""Tests T1 frente R — coletor multi-source com dedup."""
from __future__ import annotations

from unittest.mock import patch

from kiro_dash.backends.ide_sessions import IdeSessionBackend
from kiro_dash.models import Session
from kiro_dash.sources import (
    VALID_SOURCES,
    Sources,
    _dedupe_by_session_id,
    collect_sessions,
)
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


def _make_session(sid: str, agent: str = "test") -> Session:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    return Session(
        session_id=sid,
        title="t",
        agent_name=agent,
        model_id="m",
        rate_multiplier=1.0,
        context_window_tokens=200_000,
        cwd="/tmp",
        created_at=now,
        updated_at=now,
        version="v1",
        session_created_reason=None,
        is_active=False,
        turns=[],
    )


# ── _dedupe_by_session_id ────────────────────────────────────────────


def test_dedupe_empty_returns_empty():
    assert _dedupe_by_session_id([]) == []


def test_dedupe_no_dupes_preserves_order():
    a = _make_session("a")
    b = _make_session("b")
    c = _make_session("c")
    assert _dedupe_by_session_id([a, b, c]) == [a, b, c]


def test_dedupe_keeps_first_occurrence():
    a1 = _make_session("a", agent="cli")
    a2 = _make_session("a", agent="ide")
    result = _dedupe_by_session_id([a1, a2])
    assert len(result) == 1
    assert result[0].agent_name == "cli"  # primeira vence


def test_dedupe_cross_slug_does_not_collide():
    """CLI e IDE têm slugs distintos — sem colisão real."""
    cli_s = _make_session("8e2c534f-0296-4bc8-9048-196ca3521378")
    ide_s = _make_session("ide-sessions:8e2c534f-0296-4bc8-9048-196ca3521378")
    result = _dedupe_by_session_id([cli_s, ide_s])
    assert len(result) == 2  # ambos preservados


# ── collect_sessions ────────────────────────────────────────────────


def test_valid_sources_constant():
    assert VALID_SOURCES == ("cli", "ide", "all")


def test_collect_sessions_cli_only():
    with patch(
        "kiro_dash.parser.load_all_sessions",
        return_value=[_make_session("cli-1")],
    ):
        result = collect_sessions("cli")
    assert len(result) == 1
    assert result[0].session_id == "cli-1"


def test_collect_sessions_ide_only(tmp_path):
    sources = _ide_only_sources(tmp_path)
    result = collect_sessions("ide", sources=sources)
    assert len(result) == 1
    assert result[0].session_id == f"ide-sessions:{SESSION_ID}"


def test_collect_sessions_all_concatenates(tmp_path):
    sources = _ide_only_sources(tmp_path)
    with patch(
        "kiro_dash.parser.load_all_sessions",
        return_value=[_make_session("cli-1")],
    ):
        result = collect_sessions("all", sources=sources)
    assert len(result) == 2
    ids = {s.session_id for s in result}
    assert "cli-1" in ids
    assert f"ide-sessions:{SESSION_ID}" in ids


def test_collect_sessions_all_dedupes_within_slug(tmp_path):
    """Mesmo session_id duplicado é deduped."""
    sources = Sources(cli_json=None, ide_state=None, ide_sessions=None)
    duped_cli = [_make_session("dupe"), _make_session("dupe")]
    with patch("kiro_dash.parser.load_all_sessions", return_value=duped_cli):
        result = collect_sessions("all", sources=sources)
    assert len(result) == 1


def test_collect_sessions_dedupe_off_preserves_dupes():
    sources = Sources(cli_json=None, ide_state=None, ide_sessions=None)
    duped_cli = [_make_session("dupe"), _make_session("dupe")]
    with patch("kiro_dash.parser.load_all_sessions", return_value=duped_cli):
        result = collect_sessions("all", sources=sources, dedupe=False)
    assert len(result) == 2


def test_collect_sessions_invalid_source_falls_back_to_cli():
    with patch(
        "kiro_dash.parser.load_all_sessions",
        return_value=[_make_session("cli-1")],
    ):
        result = collect_sessions("bogus")  # type: ignore[arg-type]
    assert len(result) == 1
    assert result[0].session_id == "cli-1"


def test_collect_sessions_no_dedupe_in_cli_only():
    """dedupe só age em ``all``; ``cli`` retorna como vier."""
    sources = Sources(cli_json=None, ide_state=None, ide_sessions=None)
    duped = [_make_session("dupe"), _make_session("dupe")]
    with patch("kiro_dash.parser.load_all_sessions", return_value=duped):
        result = collect_sessions("cli", sources=sources, dedupe=True)
    # Em "cli" puro, dedupe NÃO age (concatenação não acontece)
    assert len(result) == 2


def test_collect_sessions_ide_unavailable_returns_empty():
    sources = Sources(cli_json=None, ide_state=None, ide_sessions=None)
    result = collect_sessions("ide", sources=sources)
    assert result == []
