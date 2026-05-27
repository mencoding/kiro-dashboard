"""Tests T5+T6 W7 — TUI seletor source + badge saldo no subtitle."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from kiro_dash.backends.ide_state import IdeUsageState
from kiro_dash.sources import Sources
from kiro_dash.views.app import _SOURCE_CYCLE, KiroDashApp, _build_subtitle


def _fake_ide_state(age_seconds: float = 60.0) -> IdeUsageState:
    now = datetime.now(timezone.utc)
    return IdeUsageState(
        current_usage=1598.0,
        usage_limit=10000.0,
        percentage_used=15.98,
        current_overages=0.0,
        overage_cap=0.0,
        overage_charges=0.0,
        overage_rate=0.04,
        reset_date=now + timedelta(days=10),
        currency_code="USD",
        currency_symbol="$",
        unit="INVOCATIONS",
        type="CREDIT",
        timestamp=now - timedelta(seconds=age_seconds),
        schema_version_observed=1,
    )


# ── _build_subtitle ──────────────────────────────────────────────────


def test_build_subtitle_with_no_ide():
    sources = Sources(cli_json=None, ide_state=None, ide_sessions=None)
    sub = _build_subtitle("all", sources)
    assert "source=all" in sub
    assert "saldo" not in sub


def test_build_subtitle_with_ide_includes_balance():
    state = _fake_ide_state(age_seconds=60)
    backend = MagicMock()
    backend.read_usage_state.return_value = state
    sources = Sources(cli_json=None, ide_state=backend, ide_sessions=None)
    sub = _build_subtitle("all", sources)
    assert "source=all" in sub
    assert "saldo:" in sub
    assert "1598" in sub
    assert "10000" in sub
    assert "15.98%" in sub
    assert "[green" in sub  # idade 60s = green


def test_build_subtitle_uses_freshness_color_yellow():
    state = _fake_ide_state(age_seconds=4 * 3600)  # 4h
    backend = MagicMock()
    backend.read_usage_state.return_value = state
    sources = Sources(cli_json=None, ide_state=backend, ide_sessions=None)
    sub = _build_subtitle("all", sources)
    assert "[yellow" in sub


def test_build_subtitle_uses_freshness_color_red():
    state = _fake_ide_state(age_seconds=15 * 3600)  # 15h
    backend = MagicMock()
    backend.read_usage_state.return_value = state
    sources = Sources(cli_json=None, ide_state=backend, ide_sessions=None)
    sub = _build_subtitle("all", sources)
    assert "[red" in sub


def test_build_subtitle_uses_freshness_color_gray():
    state = _fake_ide_state(age_seconds=30 * 3600)  # 30h
    backend = MagicMock()
    backend.read_usage_state.return_value = state
    sources = Sources(cli_json=None, ide_state=backend, ide_sessions=None)
    sub = _build_subtitle("all", sources)
    assert "[gray" in sub


def test_build_subtitle_handles_ide_state_error():
    """Se read_usage_state levanta, subtitle só mostra source."""
    from kiro_dash.backends.ide_state import IdeStateError

    backend = MagicMock()
    backend.read_usage_state.side_effect = IdeStateError("schema unknown")
    sources = Sources(cli_json=None, ide_state=backend, ide_sessions=None)
    sub = _build_subtitle("all", sources)
    assert "source=all" in sub
    assert "saldo" not in sub


# ── KiroDashApp source cycle ────────────────────────────────────────


def test_source_cycle_constant():
    assert _SOURCE_CYCLE == ("all", "cli", "ide")


def test_app_initial_source_is_all():
    app = KiroDashApp()
    assert app.current_source == "all"


def test_action_cycle_source_advances():
    app = KiroDashApp()
    # Mockar _refresh_subtitle e notify para evitar Textual runtime
    app._refresh_subtitle = MagicMock()  # type: ignore[method-assign]
    app.notify = MagicMock()  # type: ignore[method-assign]

    app.current_source = "all"
    app.action_cycle_source()
    assert app.current_source == "cli"

    app.action_cycle_source()
    assert app.current_source == "ide"

    app.action_cycle_source()
    assert app.current_source == "all"  # wrap


def test_action_cycle_source_calls_notify():
    app = KiroDashApp()
    app._refresh_subtitle = MagicMock()  # type: ignore[method-assign]
    app.notify = MagicMock()  # type: ignore[method-assign]
    app.current_source = "all"
    app.action_cycle_source()
    app.notify.assert_called_once()
    args, kwargs = app.notify.call_args
    assert "source = cli" in args[0]


def test_app_imports_without_crash():
    """Smoke: KiroDashApp e helpers importam OK."""
    from kiro_dash.views.app import (
        KiroDashApp,
        _SOURCE_CYCLE,
        _build_subtitle,
        run_app,
    )

    assert KiroDashApp is not None
    assert _SOURCE_CYCLE
    assert callable(_build_subtitle)
    assert callable(run_app)
