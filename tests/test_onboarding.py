"""Testes do banner de onboarding."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from kiro_dash.onboarding import (
    format_ide_banner_text,
    is_banner_suppressed_by_env,
    mark_ide_banner_shown,
    should_show_ide_banner,
)


def test_should_show_when_only_cli_and_no_state(tmp_path):
    state = tmp_path / "banner_state.json"
    assert should_show_ide_banner(has_only_cli=True, state_path=state) is True


def test_should_not_show_when_ide_present(tmp_path):
    state = tmp_path / "banner_state.json"
    assert should_show_ide_banner(has_only_cli=False, state_path=state) is False


def test_should_not_show_when_env_suppressed(tmp_path, monkeypatch):
    monkeypatch.setenv("KIRO_DASH_NO_BANNER", "1")
    state = tmp_path / "banner_state.json"
    assert should_show_ide_banner(has_only_cli=True, state_path=state) is False
    assert is_banner_suppressed_by_env() is True


def test_should_show_when_env_not_one(tmp_path, monkeypatch):
    """Apenas o valor exato '1' suprime; outros são ignorados."""
    monkeypatch.setenv("KIRO_DASH_NO_BANNER", "true")
    state = tmp_path / "banner_state.json"
    # Não suprime — só "1" suprime
    assert should_show_ide_banner(has_only_cli=True, state_path=state) is True


def test_mark_shown_persists_today(tmp_path):
    state = tmp_path / "banner_state.json"
    fixed_now = datetime(2026, 5, 27, 18, 0, tzinfo=timezone.utc)
    mark_ide_banner_shown(now=fixed_now, state_path=state)
    payload = json.loads(state.read_text(encoding="utf-8"))
    today = fixed_now.astimezone().date().isoformat()
    assert payload["ide_install"]["last_shown"] == today


def test_should_not_show_again_same_day(tmp_path):
    state = tmp_path / "banner_state.json"
    fixed_now = datetime(2026, 5, 27, 18, 0, tzinfo=timezone.utc)
    mark_ide_banner_shown(now=fixed_now, state_path=state)
    assert should_show_ide_banner(
        has_only_cli=True, now=fixed_now, state_path=state
    ) is False


def test_should_show_again_next_day(tmp_path):
    state = tmp_path / "banner_state.json"
    day1 = datetime(2026, 5, 27, 18, 0, tzinfo=timezone.utc)
    mark_ide_banner_shown(now=day1, state_path=state)

    day2 = datetime(2026, 5, 28, 9, 0, tzinfo=timezone.utc)
    assert should_show_ide_banner(
        has_only_cli=True, now=day2, state_path=state
    ) is True


def test_format_banner_text_contains_install_url():
    text = format_ide_banner_text()
    assert "kiro.dev" in text
    assert "KIRO_DASH_NO_BANNER" in text
    assert "estimativa local" in text


def test_state_path_handles_corrupted_file(tmp_path):
    state = tmp_path / "banner_state.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text("{ corrupted json", encoding="utf-8")
    # Deve voltar a mostrar (state corrompido = sem registro)
    assert should_show_ide_banner(has_only_cli=True, state_path=state) is True
