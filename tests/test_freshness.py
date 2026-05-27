"""Testes do helper de frescor (ADR-0001 §"Política de frescor")."""
from __future__ import annotations

import pytest

from kiro_dash.freshness import (
    DEFAULT_THRESHOLDS,
    FreshnessLevel,
    FreshnessThresholds,
    format_age,
    format_freshness_badge,
    freshness_for,
    freshness_message,
)


# --- freshness_for ---


@pytest.mark.parametrize(
    "age_h,expected",
    [
        (0.0, FreshnessLevel.GREEN),
        (1.0, FreshnessLevel.GREEN),
        (2.999, FreshnessLevel.GREEN),
        (3.0, FreshnessLevel.YELLOW),
        (5.0, FreshnessLevel.YELLOW),
        (11.999, FreshnessLevel.YELLOW),
        (12.0, FreshnessLevel.RED),
        (18.0, FreshnessLevel.RED),
        (23.999, FreshnessLevel.RED),
        (24.0, FreshnessLevel.GRAY),
        (48.0, FreshnessLevel.GRAY),
        (168.0, FreshnessLevel.GRAY),
    ],
)
def test_freshness_for_default_thresholds(age_h, expected):
    assert freshness_for(age_h * 3600.0) is expected


def test_freshness_for_negative_normalizes_to_green():
    # clock skew (now atrás do timestamp) não deve quebrar
    assert freshness_for(-100.0) is FreshnessLevel.GREEN


def test_freshness_for_custom_thresholds():
    custom = FreshnessThresholds(
        green_max_hours=1.0,
        yellow_max_hours=4.0,
        red_max_hours=8.0,
    )
    assert freshness_for(0.5 * 3600, custom) is FreshnessLevel.GREEN
    assert freshness_for(2.0 * 3600, custom) is FreshnessLevel.YELLOW
    assert freshness_for(6.0 * 3600, custom) is FreshnessLevel.RED
    assert freshness_for(10.0 * 3600, custom) is FreshnessLevel.GRAY


def test_default_thresholds_are_3_12_24():
    assert DEFAULT_THRESHOLDS.green_max_hours == 3.0
    assert DEFAULT_THRESHOLDS.yellow_max_hours == 12.0
    assert DEFAULT_THRESHOLDS.red_max_hours == 24.0


# --- format_age ---


@pytest.mark.parametrize(
    "seconds,expected",
    [
        (0, "0s"),
        (1, "1s"),
        (45, "45s"),
        (59, "59s"),
        (60, "1m"),
        (180, "3m"),
        (3599, "59m"),
        (3600, "1h"),
        (7200, "2h"),
        (86399, "23h"),
        (86400, "1d"),
        (172800, "2d"),
    ],
)
def test_format_age(seconds, expected):
    assert format_age(seconds) == expected


def test_format_age_negative_normalizes_to_zero():
    assert format_age(-100) == "0s"


# --- format_freshness_badge ---


def test_badge_without_color_is_plain_text():
    badge = format_freshness_badge(FreshnessLevel.GREEN, 47, with_color=False)
    assert badge == "[verde · 47s atrás]"


def test_badge_with_color_uses_rich_markup():
    badge = format_freshness_badge(FreshnessLevel.YELLOW, 7200, with_color=True)
    # Estrutura: [yellow]\[amarelo · 2h atrás][/yellow]
    assert badge.startswith("[yellow]")
    assert badge.endswith("[/yellow]")
    assert "amarelo · 2h atrás" in badge


def test_badge_labels_are_in_portuguese():
    assert "verde" in format_freshness_badge(FreshnessLevel.GREEN, 0, with_color=False)
    assert "amarelo" in format_freshness_badge(FreshnessLevel.YELLOW, 0, with_color=False)
    assert "vermelho" in format_freshness_badge(FreshnessLevel.RED, 0, with_color=False)
    assert "cinza" in format_freshness_badge(FreshnessLevel.GRAY, 0, with_color=False)


# --- freshness_message ---


def test_message_green_is_empty():
    assert freshness_message(FreshnessLevel.GREEN, 60) == ""


def test_message_yellow_just_age():
    msg = freshness_message(FreshnessLevel.YELLOW, 7200)
    assert msg == "snapshot de 2h atrás"


def test_message_red_includes_refresh_hint():
    msg = freshness_message(FreshnessLevel.RED, 18 * 3600)
    assert "abra o Kiro IDE" in msg
    assert "18h" in msg


def test_message_gray_warns_stale():
    msg = freshness_message(FreshnessLevel.GRAY, 3 * 86400)
    assert "stale" in msg.lower()
    assert "3d" in msg
