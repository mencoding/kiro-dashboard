"""Tests T1+T2 W8 — filtro source nas tabs + card de saldo Now."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from kiro_dash.backends.ide_state import IdeUsageState
from kiro_dash.sources import Sources
from kiro_dash.views.tabs._helpers import collect_for_tab, get_current_source
from kiro_dash.views.tabs.now_tab import _build_balance_card


# ── _helpers ─────────────────────────────────────────────────────────


def test_get_current_source_default_all_when_no_app():
    widget = MagicMock(spec=[])  # sem .app
    assert get_current_source(widget) == "all"


def test_get_current_source_reads_app_attribute():
    widget = MagicMock()
    widget.app.current_source = "ide"
    assert get_current_source(widget) == "ide"


def test_get_current_source_default_when_app_lacks_attr():
    widget = MagicMock()
    del widget.app.current_source
    # MagicMock cria atributos sob demanda; vamos usar plain object
    class FakeApp:
        pass

    class FakeWidget:
        app = FakeApp()

    assert get_current_source(FakeWidget()) == "all"


def test_collect_for_tab_uses_current_source():
    """collect_for_tab passa source para sources.collect_sessions."""
    widget = MagicMock()
    widget.app.current_source = "cli"
    with patch("kiro_dash.sources.collect_sessions") as cs:
        cs.return_value = []
        collect_for_tab(widget)
    cs.assert_called_once_with("cli")


# ── _build_balance_card ──────────────────────────────────────────────


def _fake_state(usage: float = 1598.0, limit: float = 10000.0, age: float = 60) -> IdeUsageState:
    now = datetime.now(timezone.utc)
    return IdeUsageState(
        current_usage=usage,
        usage_limit=limit,
        percentage_used=usage / limit * 100.0,
        current_overages=0.0,
        overage_cap=0.0,
        overage_charges=0.0,
        overage_rate=0.04,
        reset_date=now + timedelta(days=10),
        currency_code="USD",
        currency_symbol="$",
        unit="INVOCATIONS",
        type="CREDIT",
        timestamp=now - timedelta(seconds=age),
        schema_version_observed=1,
    )


def test_balance_card_empty_when_no_ide():
    sources = Sources(cli_json=None, ide_state=None, ide_sessions=None)
    assert _build_balance_card(sources) == ""


def test_balance_card_empty_on_ide_state_error():
    backend = MagicMock()
    backend.read_usage_state.side_effect = type("Err", (Exception,), {})("oops")
    # Adapt to IdeStateError
    from kiro_dash.backends.ide_state import IdeStateError

    backend.read_usage_state.side_effect = IdeStateError("schema")
    sources = Sources(cli_json=None, ide_state=backend, ide_sessions=None)
    assert _build_balance_card(sources) == ""


def test_balance_card_renders_with_state():
    backend = MagicMock()
    backend.read_usage_state.return_value = _fake_state(age=60)
    sources = Sources(cli_json=None, ide_state=backend, ide_sessions=None)
    card = _build_balance_card(sources)
    assert "Saldo Kiro IDE" in card
    assert "1598" in card
    assert "10000" in card
    assert "15.98%" in card
    assert "[green" in card  # idade 60s = green
    assert "Reset:" in card
    assert "Overage:" in card


def test_balance_card_uses_red_pct_color_when_above_95():
    backend = MagicMock()
    backend.read_usage_state.return_value = _fake_state(usage=9700, limit=10000, age=60)
    sources = Sources(cli_json=None, ide_state=backend, ide_sessions=None)
    card = _build_balance_card(sources)
    # 97% → pct_color red
    assert "[red]" in card


def test_balance_card_uses_yellow_pct_color_when_above_80():
    backend = MagicMock()
    backend.read_usage_state.return_value = _fake_state(usage=8500, limit=10000, age=60)
    sources = Sources(cli_json=None, ide_state=backend, ide_sessions=None)
    card = _build_balance_card(sources)
    assert "[yellow]" in card


def test_balance_card_freshness_color_yellow():
    backend = MagicMock()
    backend.read_usage_state.return_value = _fake_state(age=4 * 3600)  # 4h
    sources = Sources(cli_json=None, ide_state=backend, ide_sessions=None)
    card = _build_balance_card(sources)
    assert "[yellow · 4h" in card  # freshness yellow


def test_balance_card_freshness_color_red():
    backend = MagicMock()
    backend.read_usage_state.return_value = _fake_state(age=15 * 3600)  # 15h
    sources = Sources(cli_json=None, ide_state=backend, ide_sessions=None)
    card = _build_balance_card(sources)
    assert "[red · 15h" in card


def test_balance_card_includes_progress_bar():
    """Card tem bar_inline ou caracteres de barra."""
    backend = MagicMock()
    backend.read_usage_state.return_value = _fake_state(usage=5000, limit=10000, age=60)
    sources = Sources(cli_json=None, ide_state=backend, ide_sessions=None)
    card = _build_balance_card(sources)
    # bar_inline usa caracteres unicode de bloco
    assert "█" in card or "▓" in card or "▒" in card or "░" in card
