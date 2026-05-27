"""TUI Textual do kiro-dash — 6 abas, refresh manual.

Wave 7 (T5+T6):

- ``current_source`` cycle via tecla ``s`` (estado visual; tabs
  continuam lendo todas as fontes por default em v0.7.0; iterações
  futuras vão filtrar por aba).
- Badge de saldo + frescor no ``sub_title`` quando IDE detectado.
"""
from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, TabbedContent, TabPane

from kiro_dash import __version__
from kiro_dash.backends import Capability
from kiro_dash.backends.ide_state import IdeStateError
from kiro_dash.freshness import format_age, freshness_for
from kiro_dash.sources import Sources
from kiro_dash.views.tabs.history_tab import HistoryTab
from kiro_dash.views.tabs.models_tab import ModelsTab
from kiro_dash.views.tabs.now_tab import NowTab
from kiro_dash.views.tabs.projects_tab import ProjectsTab
from kiro_dash.views.tabs.session_tab import SessionTab
from kiro_dash.views.tabs.today_tab import TodayTab
from kiro_dash.views.tabs.tools_tab import ToolsTab

_SOURCE_CYCLE = ("all", "cli", "ide")


def _build_subtitle(source: str, sources_obj: Sources | None = None) -> str:
    """Constrói subtítulo do header com source atual + badge de saldo IDE.

    Formato: ``"source=all · saldo: 1598/10000 (15.99%) [verde · 47s]"``.
    Se IDE indisponível: apenas ``"source=<x>"``.
    """
    parts: list[str] = [f"source={source}"]
    s = sources_obj if sources_obj is not None else Sources.detect()
    if s.ide_state is not None:
        try:
            state = s.ide_state.read_usage_state()  # type: ignore[attr-defined]
        except IdeStateError:
            state = None
        if state is not None:
            level = freshness_for(state.age_seconds)
            badge = f"[{level.value} · {format_age(state.age_seconds)}]"
            parts.append(
                f"saldo: {state.current_usage:.0f}/{state.usage_limit:.0f} "
                f"({state.percentage_used:.2f}%) {badge}"
            )
    return "  ·  ".join(parts)


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
        Binding("7", "show_tab('history')", "History"),
        Binding("r", "refresh_active", "Refresh"),
        Binding("s", "cycle_source", "Source"),
        Binding("q", "quit", "Sair"),
        Binding("question_mark", "help", "Ajuda"),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_source: str = "all"
        self._sources_cached: Sources | None = None

    def _sources(self) -> Sources:
        """Cache simples de Sources.detect() para o subtitle."""
        if self._sources_cached is None:
            self._sources_cached = Sources.detect()
        return self._sources_cached

    def _refresh_subtitle(self) -> None:
        self.sub_title = _build_subtitle(self.current_source, self._sources())

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
            with TabPane("History", id="history"):
                yield HistoryTab()
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_subtitle()

    def action_show_tab(self, tab_id: str) -> None:
        self.query_one(TabbedContent).active = tab_id

    def action_refresh_active(self) -> None:
        # Refresh do subtitle (saldo pode ter mudado)
        self._sources_cached = None
        self._refresh_subtitle()
        active = self.query_one(TabbedContent).active
        pane = self.query_one(f"#{active}", TabPane)
        for child in pane.children:
            if hasattr(child, "refresh_snapshot"):
                child.refresh_snapshot()  # type: ignore[attr-defined]

    def action_cycle_source(self) -> None:
        """Cycle source (T5-W7 → T1-W8 funcional).

        Em v0.7.1+ o source filtra de fato as tabs Now/Today/Projects/
        Models/Tools (cada tab lê ``self.app.current_source`` via
        ``views.tabs._helpers.collect_for_tab``). Cycle dispara
        refresh em todas as tabs visíveis após mudança.
        """
        idx = _SOURCE_CYCLE.index(self.current_source)
        self.current_source = _SOURCE_CYCLE[(idx + 1) % len(_SOURCE_CYCLE)]
        self._refresh_subtitle()
        self.notify(
            f"source = {self.current_source}",
            title="Filtro de fonte",
            timeout=3,
        )
        self._refresh_all_tabs()

    def _refresh_all_tabs(self) -> None:
        """Dispara ``refresh_snapshot`` em todas as tabs com dados."""
        for tab_id in ("now", "today", "projects", "models", "tools"):
            try:
                pane = self.query_one(f"#{tab_id}", TabPane)
            except Exception:
                continue
            for child in pane.children:
                if hasattr(child, "refresh_snapshot"):
                    try:
                        child.refresh_snapshot()  # type: ignore[attr-defined]
                    except Exception:
                        # Não bloquear o cycle por uma tab quebrada
                        pass

    def action_help(self) -> None:
        """Abre modal completo com lista de atalhos (T6-W8)."""
        from kiro_dash.views.help_modal import HelpModal

        self.push_screen(HelpModal())


def run_app() -> int:
    """Entry para o subcomando ``kiro-dash tui``."""
    app = KiroDashApp()
    app.run()
    return 0
