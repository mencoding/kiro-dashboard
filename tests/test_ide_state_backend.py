"""Testes do IdeStateBackend (state.vscdb do Kiro IDE)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from kiro_dash.backends import Capability
from kiro_dash.backends.ide_state import (
    IdeStateBackend,
    IdeStateSchemaError,
    IdeUsageState,
)
from tests.fixtures.ide.build_state_vscdb import build_state_vscdb


def test_slug_and_capabilities():
    b = IdeStateBackend(db_path=Path("/nonexistent.vscdb"))
    assert b.slug == "ide"
    assert b.capabilities() == {Capability.USAGE_STATE}


def test_is_available_false_for_missing_file(tmp_path):
    b = IdeStateBackend(db_path=tmp_path / "missing.vscdb")
    assert b.is_available() is False
    assert b.read_usage_state() is None
    assert b.data_age() is None


def test_is_available_false_when_kiro_agent_key_absent(tmp_path):
    db = build_state_vscdb(tmp_path, omit_kiro_agent=True)
    b = IdeStateBackend(db_path=db)
    assert b.is_available() is False
    assert b.read_usage_state() is None


def test_is_available_true_with_default_fixture(tmp_path):
    db = build_state_vscdb(tmp_path)
    b = IdeStateBackend(db_path=db)
    assert b.is_available() is True


def test_read_usage_state_default_fixture(tmp_path):
    db = build_state_vscdb(tmp_path)
    b = IdeStateBackend(db_path=db)
    state = b.read_usage_state()
    assert isinstance(state, IdeUsageState)
    assert state.current_usage == 100.0
    assert state.usage_limit == 1000.0
    assert state.percentage_used == 10.0
    assert state.current_overages == 0.0
    assert state.overage_cap == 10000.0
    assert state.overage_rate == 0.04
    assert state.currency_code == "USD"
    assert state.currency_symbol == "$"
    assert state.unit == "INVOCATIONS"
    assert state.type == "CREDIT"
    assert state.schema_version_observed == 1
    assert state.reset_date.year == 2026
    assert state.reset_date.month == 6
    assert state.reset_date.day == 1
    assert state.reset_date.tzinfo is not None
    # timestamp em UTC
    assert state.timestamp.tzinfo is not None


def test_age_seconds_consistent_with_now(tmp_path):
    db = build_state_vscdb(tmp_path)
    b = IdeStateBackend(db_path=db)
    state = b.read_usage_state()
    assert state is not None
    age = state.age_seconds
    # fixture timestamp = 1779900000000 ms (2026-05-27T13:20:00 UTC)
    # idade tem que ser positiva e finita
    assert age >= 0
    assert age == pytest.approx(b.data_age(), rel=1e-3)


def test_schema_error_when_usage_state_field_missing(tmp_path):
    custom = {"hasBeenInstalled": True}  # falta o campo crítico
    db = build_state_vscdb(tmp_path, kiro_agent_data=custom)
    b = IdeStateBackend(db_path=db)
    # is_available captura erro silenciosamente
    assert b.is_available() is False
    # read_usage_state propaga o erro
    with pytest.raises(IdeStateSchemaError) as ei:
        b.read_usage_state()
    assert "usageState" in str(ei.value)


def test_schema_error_when_breakdowns_empty(tmp_path):
    custom = {
        "hasBeenInstalled": True,
        "kiro.resourceNotifications.usageState": {
            "usageBreakdowns": [],
            "timestamp": 1779900000000,
        },
    }
    db = build_state_vscdb(tmp_path, kiro_agent_data=custom)
    b = IdeStateBackend(db_path=db)
    with pytest.raises(IdeStateSchemaError):
        b.read_usage_state()


def test_schema_error_when_required_fields_missing(tmp_path):
    custom = {
        "hasBeenInstalled": True,
        "kiro.resourceNotifications.usageState": {
            "usageBreakdowns": [
                {
                    "currentUsage": 50.0,
                    # falta usageLimit, percentageUsed, resetDate, currency, unit
                }
            ],
            "timestamp": 1779900000000,
        },
    }
    db = build_state_vscdb(tmp_path, kiro_agent_data=custom)
    b = IdeStateBackend(db_path=db)
    with pytest.raises(IdeStateSchemaError) as ei:
        b.read_usage_state()
    assert "obrigatório" in str(ei.value) or "faltando" in str(ei.value)


def test_schema_error_when_timestamp_missing(tmp_path):
    custom = {
        "hasBeenInstalled": True,
        "kiro.resourceNotifications.usageState": {
            "usageBreakdowns": [
                {
                    "currentUsage": 50.0,
                    "usageLimit": 1000,
                    "percentageUsed": 5.0,
                    "resetDate": "2026-06-01T00:00:00.000Z",
                    "currency": {"code": "USD", "symbol": "$"},
                    "unit": "INVOCATIONS",
                }
            ],
            # timestamp ausente
        },
    }
    db = build_state_vscdb(tmp_path, kiro_agent_data=custom)
    b = IdeStateBackend(db_path=db)
    with pytest.raises(IdeStateSchemaError):
        b.read_usage_state()


def test_extra_keys_dont_break_reader(tmp_path):
    db = build_state_vscdb(
        tmp_path,
        extra_keys={"telemetryClientId": "abc", "colorThemeData": "{}"},
    )
    b = IdeStateBackend(db_path=db)
    assert b.is_available() is True
    state = b.read_usage_state()
    assert state is not None
    assert state.current_usage == 100.0


def test_kiro_agent_with_unknown_extra_top_level_keys(tmp_path):
    """Adicionar campo top-level novo não derruba o parser."""
    custom = {
        "hasBeenInstalled": True,
        "kiro.resourceNotifications.usageState": {
            "usageBreakdowns": [
                {
                    "currency": {"code": "USD", "symbol": "$"},
                    "currentOverages": 0,
                    "currentUsage": 50.0,
                    "displayName": "Credit",
                    "displayNamePlural": "Credits",
                    "percentageUsed": 5.0,
                    "overageCap": 10000,
                    "overageCharges": 0,
                    "overageRate": 0.04,
                    "resetDate": "2026-06-01T00:00:00.000Z",
                    "type": "CREDIT",
                    "unit": "INVOCATIONS",
                    "usageLimit": 1000,
                    "futureFieldX": "to be ignored",
                }
            ],
            "timestamp": 1779900000000,
            "futureUsageStateField": True,
        },
        "kiro.coach.shown.autopilot": True,
        "kiro.coach.shown.policy": True,
        "kiro.someFutureFlag": "xyz",
    }
    db = build_state_vscdb(tmp_path, kiro_agent_data=custom)
    b = IdeStateBackend(db_path=db)
    assert b.is_available() is True
    state = b.read_usage_state()
    assert state is not None
    assert state.current_usage == 50.0
