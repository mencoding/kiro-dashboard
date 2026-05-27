"""Smoke test da KiroDashApp — usa App.run_test() do Textual."""
from __future__ import annotations

import pytest
from textual.widgets import TabbedContent

from kiro_dash.views.app import KiroDashApp


@pytest.mark.asyncio
async def test_app_starts_with_now_active():
    app = KiroDashApp()
    async with app.run_test() as pilot:
        tabbed = pilot.app.query_one(TabbedContent)
        assert tabbed.active == "now"


@pytest.mark.asyncio
async def test_keys_switch_tabs():
    app = KiroDashApp()
    async with app.run_test() as pilot:
        await pilot.press("2")
        await pilot.pause()
        tabbed = pilot.app.query_one(TabbedContent)
        assert tabbed.active == "today"
        await pilot.press("4")
        await pilot.pause()
        assert tabbed.active == "models"


@pytest.mark.asyncio
async def test_r_does_not_crash_on_each_tab():
    app = KiroDashApp()
    async with app.run_test() as pilot:
        for tab_key in ("1", "2", "3", "4", "5", "6", "7"):
            await pilot.press(tab_key)
            await pilot.pause()
            await pilot.press("r")
            await pilot.pause()
