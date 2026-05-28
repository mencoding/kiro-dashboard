"""Regression test — HelpModal não deve crash ao montar.

Bug v0.7.1: passava ``header_style="bold"`` ao DataTable da Textual
(API do rich.Table). Fixado em v0.7.2 movendo bold para tcss.
"""
from __future__ import annotations

import pytest
from textual.app import App

from kiro_dash.views.help_modal import HelpModal


class _Harness(App):
    """App mínimo que abre o modal no on_mount."""

    def on_mount(self) -> None:
        self.push_screen(HelpModal())


@pytest.mark.asyncio
async def test_help_modal_mounts_without_crash():
    """Garante que HelpModal compõe sem TypeError (regressão v0.7.1)."""
    app = _Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        # Modal está em screens; conferir que existe e tem o body
        assert isinstance(app.screen, HelpModal)
        body = app.screen.query_one("#help-modal-body")
        assert body is not None


@pytest.mark.asyncio
async def test_help_modal_table_has_11_rows():
    """Tabela do help tem 11 atalhos documentados."""
    app = _Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        from textual.widgets import DataTable

        table = app.screen.query_one("#help-table", DataTable)
        # Header populado + 11 keys (1-7, r, s, ?, q)
        assert table.row_count == 11


@pytest.mark.asyncio
async def test_help_modal_dismisses_on_escape():
    """ESC fecha o modal e volta para a tela anterior."""
    app = _Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, HelpModal)
        await pilot.press("escape")
        await pilot.pause()
        # Após dismiss, screen volta para a Screen default do App
        assert not isinstance(app.screen, HelpModal)


@pytest.mark.asyncio
async def test_help_modal_dismisses_on_q():
    """Tecla ``q`` também fecha o modal."""
    app = _Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("q")
        await pilot.pause()
        assert not isinstance(app.screen, HelpModal)
