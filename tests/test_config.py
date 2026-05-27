"""Testes do módulo config — round-trip TOML + defaults por tier."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from kiro_dash.config import (
    DEFAULT_MONTHLY_CREDITS,
    PlanConfig,
    default_config_path,
    load_plan,
    save_plan,
)


def test_default_monthly_credits_for_known_tiers():
    assert DEFAULT_MONTHLY_CREDITS["free"] == 50
    assert DEFAULT_MONTHLY_CREDITS["pro"] == 1000
    assert DEFAULT_MONTHLY_CREDITS["pro+"] == 2000
    assert DEFAULT_MONTHLY_CREDITS["power"] == 10000
    assert "enterprise" in DEFAULT_MONTHLY_CREDITS


def test_load_plan_returns_default_when_file_missing(tmp_path):
    cfg_path = tmp_path / "missing.toml"
    plan = load_plan(cfg_path)
    assert plan.tier == "free"
    assert plan.monthly_credits == 50
    assert plan.cycle_start == date.today().replace(day=1)


def test_save_then_load_round_trip(tmp_path):
    cfg_path = tmp_path / "config.toml"
    original = PlanConfig(
        tier="pro+",
        monthly_credits=2500,
        cycle_start=date(2026, 5, 1),
    )
    save_plan(original, cfg_path)
    loaded = load_plan(cfg_path)
    assert loaded == original


def test_save_creates_parent_dir(tmp_path):
    cfg_path = tmp_path / "deep" / "nested" / "config.toml"
    plan = PlanConfig(tier="pro", monthly_credits=1000, cycle_start=date(2026, 1, 1))
    save_plan(plan, cfg_path)
    assert cfg_path.is_file()


def test_load_uses_default_credits_when_field_missing(tmp_path):
    cfg_path = tmp_path / "partial.toml"
    cfg_path.write_text('[plan]\ntier = "pro"\n')
    plan = load_plan(cfg_path)
    assert plan.tier == "pro"
    assert plan.monthly_credits == 1000


def test_load_invalid_tier_falls_back_to_free(tmp_path):
    cfg_path = tmp_path / "bad.toml"
    cfg_path.write_text('[plan]\ntier = "ultraplus9000"\n')
    plan = load_plan(cfg_path)
    assert plan.tier == "free"


def test_default_config_path_is_under_xdg_config():
    p = default_config_path()
    assert "kiro-dash" in str(p)
    assert p.name == "config.toml"


def test_save_plan_writes_valid_toml(tmp_path):
    cfg_path = tmp_path / "out.toml"
    plan = PlanConfig(tier="power", monthly_credits=10000, cycle_start=date(2026, 6, 15))
    save_plan(plan, cfg_path)
    content = cfg_path.read_text()
    assert '[plan]' in content
    assert 'tier = "power"' in content
    assert 'monthly_credits = 10000' in content
    assert 'cycle_start = 2026-06-15' in content or 'cycle_start = "2026-06-15"' in content
