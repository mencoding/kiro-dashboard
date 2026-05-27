"""Tests T1-W7 — rate_multiplier mapping por modelo IDE."""
from __future__ import annotations

import pytest

from kiro_dash.backends.ide_mapper import (
    DEFAULT_RATE_MULTIPLIER,
    rate_multiplier_for_model,
)


@pytest.mark.parametrize(
    "model_id,expected",
    [
        ("claude-opus-4.7", 2.2),
        ("claude-opus-4.5", 2.2),
        ("claude-opus-4", 2.0),
        ("claude-sonnet-4.5", 1.0),
        ("claude-sonnet-4", 1.0),
        ("claude-haiku-4.5", 0.3),
        ("claude-haiku-4", 0.3),
        ("auto", 1.0),
        ("kiro:auto", 1.0),
    ],
)
def test_known_models_exact_match(model_id, expected):
    assert rate_multiplier_for_model(model_id) == expected


def test_unknown_model_returns_default():
    assert rate_multiplier_for_model("gpt-5") == DEFAULT_RATE_MULTIPLIER
    assert rate_multiplier_for_model("custom-model-abc") == DEFAULT_RATE_MULTIPLIER


def test_empty_model_returns_default():
    assert rate_multiplier_for_model("") == DEFAULT_RATE_MULTIPLIER


def test_prefix_match_for_versioned_variant():
    """claude-opus-4.7-20251015 deve casar com claude-opus-4.7 (2.2)."""
    assert rate_multiplier_for_model("claude-opus-4.7-20251015") == 2.2


def test_prefix_match_prefers_more_specific():
    """claude-opus-4.7-X casa com -4.7 (2.2), não -opus genérico (2.0)."""
    # claude-opus-4.7 (key "claude-opus-4.7", val 2.2) deve vencer
    # claude-opus (key "claude-opus", val 2.0)
    assert rate_multiplier_for_model("claude-opus-4.7-stable") == 2.2


def test_prefix_match_falls_back_for_partial():
    """Match deve ser claude-opus → 2.0 quando versão não casa em -4.x."""
    # "claude-opus-2" não casa em "claude-opus-4" mas casa em "claude-opus"
    assert rate_multiplier_for_model("claude-opus-2") == 2.0


def test_to_session_uses_rate_multiplier_from_table(tmp_path):
    """Integration: to_session com selected_model conhecido usa rate correto."""
    from datetime import datetime, timezone

    from kiro_dash.backends.ide_mapper import to_session
    from kiro_dash.backends.ide_sessions import IdeSession

    ide_sess = IdeSession(
        session_id="test-uuid",
        title="t",
        workspace_path="/tmp",
        date_created=datetime.now(timezone.utc),
        session_type="vibe",
        autonomy_mode="Autopilot",
        selected_model="claude-opus-4.7",
        default_model_title=None,
        history=[],
        context_usage_percentage=0.0,
        mtime=datetime.now(timezone.utc),
    )
    session = to_session(ide_sess, [])
    assert session.model_id == "claude-opus-4.7"
    assert session.rate_multiplier == 2.2


def test_to_session_auto_model_gets_default_rate(tmp_path):
    from datetime import datetime, timezone

    from kiro_dash.backends.ide_mapper import to_session
    from kiro_dash.backends.ide_sessions import IdeSession

    ide_sess = IdeSession(
        session_id="test-uuid",
        title="t",
        workspace_path="/tmp",
        date_created=datetime.now(timezone.utc),
        session_type="vibe",
        autonomy_mode="Autopilot",
        selected_model="auto",
        default_model_title=None,
        history=[],
        context_usage_percentage=0.0,
        mtime=datetime.now(timezone.utc),
    )
    session = to_session(ide_sess, [])
    assert session.model_id == "kiro:auto"
    assert session.rate_multiplier == 1.0
