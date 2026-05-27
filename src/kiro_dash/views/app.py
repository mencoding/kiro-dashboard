"""TUI Textual do kiro-dash — 6 abas, refresh manual."""
from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, TabbedContent, TabPane

from kiro_dash import __version__
from kiro_dash.views.tabs.models_tab import ModelsTab
from kiro_dash.views.tabs.now_tab import NowTab
from kiro_dash.views.tabs.projects_tab import ProjectsTab
from kiro_dash.views.tabs.session_tab import SessionTab
from kiro_dash.views.tabs.today_tab import TodayTab
from kiro_dash.views.tabs.tools_tab import ToolsTab


class KiroDashApp(App):
    """App principal."""

    CSS_PATH = "styles.tcss"
    TITLE = f"kiro-dash {__version__}"

    BINDINGS = [
        Binding("1", "show_tab('now')", "Now"),
        Binding("2", "show_tab('today')", "Today"),
        Binding("3", "show_tab('projects')", "Projects"),
        Binding("4", "show_tab('models')", "Models"),
        Binding("5", "show_tab('tools')", "Tools"),
        Binding("6", "show_tab('session')", "Session"),
        Binding("r", "refresh_active", "Refresh"),
        Binding("q", "quit", "Sair"),
        Binding("question_mark", "help", "Ajuda"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(initial="now", id="tabs"):
            with TabPane("Now", id="now"):
                yield NowTab()
            with TabPane("Today", id="today"):
                yield TodayTab()
            with TabPane("Projects", id="projects"):
                yield ProjectsTab()
            with TabPane("Models", id="models"):
                yield ModelsTab()
            with TabPane("Tools", id="tools"):
                yield ToolsTab()
            with TabPane("Session", id="session"):
                yield SessionTab()
        yield Footer()

    def action_show_tab(self, tab_id: str) -> None:
        self.query_one(TabbedContent).active = tab_id

    def action_refresh_active(self) -> None:
        active = self.query_one(TabbedContent).active
        pane = self.query_one(f"#{active}", TabPane)
        for child in pane.children:
            if hasattr(child, "refresh_snapshot"):
                child.refresh_snapshot()  # type: ignore[attr-defined]

    def action_help(self) -> None:
        self.notify(
            "Atalhos: 1-6 trocar aba; r refresh; q sair",
            title="Ajuda",
            timeout=5,
        )


def run_app() -> int:
    """Entry para o subcomando ``kiro-dash tui``."""
    app = KiroDashApp()
    app.run()
    return 0
