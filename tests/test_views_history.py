"""Smoke tests da aba History — App.run_test() headless."""
from __future__ import annotations

import pytest
from textual.widgets import TabbedContent

from kiro_dash.views.app import KiroDashApp


@pytest.mark.asyncio
async def test_history_tab_renders_via_key_7():
    app = KiroDashApp()
    async with app.run_test() as pilot:
        await pilot.press("7")
        await pilot.pause()
        tabbed = pilot.app.query_one(TabbedContent)
        assert tabbed.active == "history"


@pytest.mark.asyncio
async def test_history_tab_refresh_doesnt_crash():
    app = KiroDashApp()
    async with app.run_test() as pilot:
        await pilot.press("7")
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause()
        # Se chegou aqui sem exceção, o refresh funciona
        tabbed = pilot.app.query_one(TabbedContent)
        assert tabbed.active == "history"
