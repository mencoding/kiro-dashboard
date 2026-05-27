"""Tests T2-W7 — consolidação spec lógica em ide_mapper."""
from __future__ import annotations

from kiro_dash.backends.ide_mapper import consolidate_spec_executions
from kiro_dash.backends.ide_sessions import (
    IdeSessionBackend,
    read_execution,
)
from tests.fixtures.ide.build_ide_layout import (
    DEFAULT_PROFILE_HASH,
    EXEC_CHAT,
    EXEC_DO_SIMPLE,
    EXEC_SPEC_DISPATCH,
    EXEC_SPEC_GENERATION,
    INNER_HASH,
    build_ide_layout,
)


def _load(kiro_root, exec_id):
    return read_execution(kiro_root / DEFAULT_PROFILE_HASH / INNER_HASH / exec_id)


def test_consolidate_empty_returns_empty():
    assert consolidate_spec_executions([]) == []


def test_consolidate_no_spec_pattern_passes_through(tmp_path):
    """Sessão sem dispatcher/generation: lista inalterada."""
    kiro_root = build_ide_layout(tmp_path)
    chat = _load(kiro_root, EXEC_CHAT)
    do_simple = _load(kiro_root, EXEC_DO_SIMPLE)
    out = consolidate_spec_executions([chat, do_simple])
    assert len(out) == 2
    assert out[0].execution_id == EXEC_CHAT
    assert out[1].execution_id == EXEC_DO_SIMPLE


def test_consolidate_merges_dispatch_and_generation(tmp_path):
    """Spec dispatch (chat-agent intent=spec) + spec-generation linkadas → 1 turn."""
    kiro_root = build_ide_layout(tmp_path)
    dispatch = _load(kiro_root, EXEC_SPEC_DISPATCH)
    generation = _load(kiro_root, EXEC_SPEC_GENERATION)
    out = consolidate_spec_executions([dispatch, generation])
    assert len(out) == 1
    merged = out[0]
    # Identidade do dispatcher preservada
    assert merged.execution_id == EXEC_SPEC_DISPATCH
    # Actions concatenadas
    assert len(merged.actions) == len(dispatch.actions) + len(generation.actions)
    # Usage summary concatenado
    assert len(merged.usage_summary) == len(dispatch.usage_summary) + len(generation.usage_summary)
    # Status do final (generation)
    assert merged.status == generation.status
    # Tempo: start do dispatcher, end do generation
    assert merged.start_time == dispatch.start_time
    assert merged.end_time == generation.end_time
    # Intent classifier preservado
    assert merged.intent_result is not None
    assert merged.intent_result.classification == "spec"
    # workflow_type root é chat-agent
    assert merged.workflow_type == "chat-agent"


def test_consolidate_preserves_unrelated_executions(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    chat = _load(kiro_root, EXEC_CHAT)
    dispatch = _load(kiro_root, EXEC_SPEC_DISPATCH)
    generation = _load(kiro_root, EXEC_SPEC_GENERATION)
    do_simple = _load(kiro_root, EXEC_DO_SIMPLE)
    out = consolidate_spec_executions([chat, dispatch, generation, do_simple])
    # 4 entradas → 3 (dispatch+generation fundem)
    assert len(out) == 3
    ids = [e.execution_id for e in out]
    assert EXEC_CHAT in ids
    assert EXEC_SPEC_DISPATCH in ids  # mantém dispatcher como id da fusão
    assert EXEC_DO_SIMPLE in ids
    assert EXEC_SPEC_GENERATION not in ids  # consumida na fusão


def test_consolidate_credits_aggregate(tmp_path):
    """Total de créditos do merged == soma dos dois originais."""
    kiro_root = build_ide_layout(tmp_path)
    dispatch = _load(kiro_root, EXEC_SPEC_DISPATCH)
    generation = _load(kiro_root, EXEC_SPEC_GENERATION)
    out = consolidate_spec_executions([dispatch, generation])
    assert len(out) == 1
    expected_total = dispatch.total_credits + generation.total_credits
    assert abs(out[0].total_credits - expected_total) < 1e-6


def test_consolidate_dispatcher_alone_is_kept_raw(tmp_path):
    """Spec dispatcher sem generation linkada permanece intacto."""
    kiro_root = build_ide_layout(tmp_path)
    dispatch = _load(kiro_root, EXEC_SPEC_DISPATCH)
    out = consolidate_spec_executions([dispatch])
    assert len(out) == 1
    assert out[0].execution_id == EXEC_SPEC_DISPATCH
    assert out[0].intent_result is not None
    assert out[0].intent_result.classification == "spec"


def test_consolidate_orphan_generation_is_kept_raw(tmp_path):
    """Generation sem dispatcher anterior fica como execution standalone."""
    kiro_root = build_ide_layout(tmp_path)
    generation = _load(kiro_root, EXEC_SPEC_GENERATION)
    out = consolidate_spec_executions([generation])
    assert len(out) == 1
    assert out[0].execution_id == EXEC_SPEC_GENERATION
    assert out[0].workflow_type == "spec-generation"
