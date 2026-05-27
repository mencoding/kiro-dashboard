"""CLI ``kiro-dash`` — entry point.

Subcomandos:
    whoami   - identidade AWS / billing / profile do Kiro
    today    - agregado do dia corrente (créditos, modelo, agent, projeto)
    session  - drill-down de uma sessão (por prefixo de session_id)
    now      - live view das sessões ativas
"""
from __future__ import annotations

import signal as _signal
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import click
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from kiro_dash import __version__
from kiro_dash.account import run_whoami
from kiro_dash.aggregator import (
    Aggregate,
    AgentPairAgg,
    active_sessions,
    aggregate_by_agent,
    aggregate_by_agent_pair,
    aggregate_by_cwd,
    aggregate_by_model,
    aggregate_by_project,
    aggregate_by_session,
    aggregate_tools_in_window,
    balance_in_cycle,
    filter_by_agent,
    resolve_window,
    total_credits,
    turns_in_last_days,
    turns_in_local_day,
)
from kiro_dash.backends import Capability
from kiro_dash.backends.ide_state import IdeStateError
from kiro_dash.config import (
    DEFAULT_MONTHLY_CREDITS,
    VALID_TIERS,
    PlanConfig,
    default_config_path,
    load_aliases,
    load_plan,
    save_aliases,
    save_plan,
)
from kiro_dash.freshness import (
    FreshnessLevel,
    format_age,
    freshness_for,
    freshness_message,
)
from kiro_dash.models import Session
from kiro_dash.onboarding import (
    format_ide_banner_text,
    mark_ide_banner_shown,
    should_show_ide_banner,
)
from kiro_dash.parser import (
    DEFAULT_SESSIONS_DIR,
    discover_sessions,
    find_session_by_prefix,
    load_all_sessions,
    load_session_file,
    read_lock,
)
from kiro_dash.sync import (
    SyncConfig,
    rclone_available,
    rclone_remote_exists,
    sync_pull,
    sync_push,
)
from kiro_dash.watchdog import (
    is_session_running,
    kill_session as watchdog_kill_session,
    running_sessions,
    stuck_sessions,
)
from kiro_dash.jsonl_parser import iter_tool_calls
from kiro_dash.snapshots import ensure_snapshots_up_to, write_snapshot
from kiro_dash.sources import Sources, collect_sessions

console = Console()


# ─── helpers multi-source (Wave 6 frente Q) ──────────────────────────────


SOURCE_CHOICES = ["cli", "ide", "all"]


def _find_session_by_prefix_in_ide(
    prefix: str, sources: Sources | None = None
) -> Session | None:
    """Resolve prefixo de session_id em sessões IDE.

    Aceita prefixo do raw uuid (``5e551001-1...``) ou do composto
    (``ide-sessions:5e55...``). Retorna ``None`` se zero matches ou
    ambíguo (>1 match).
    """
    srcs = sources if sources is not None else Sources.detect()
    if srcs.ide_sessions is None:
        return None
    matches: list[Session] = []
    for s in srcs.ide_sessions.list_sessions():
        composite = s.session_id
        raw = composite.split(":", 1)[-1] if ":" in composite else composite
        if raw.startswith(prefix) or composite.startswith(prefix):
            matches.append(s)
    if len(matches) == 1:
        return matches[0]
    return None


# Backward-compat: alguns tests do CLI ainda chamam _collect_sessions_by_source.
# Em v0.7.0+ isto delega para sources.collect_sessions.
def _collect_sessions_by_source(
    source: str, sources: Sources | None = None
) -> list[Session]:
    """[Deprecated em v0.7.0] use ``kiro_dash.sources.collect_sessions``."""
    return collect_sessions(source, sources=sources)


# ─── helpers de formatação ────────────────────────────────────────────────


def _fmt_credits(value: float) -> str:
    return f"{value:.2f}"


def _fmt_duration(td) -> str:
    total_seconds = int(td.total_seconds())
    if total_seconds < 60:
        return f"{total_seconds}s"
    if total_seconds < 3600:
        m, s = divmod(total_seconds, 60)
        return f"{m}m{s:02d}s"
    h, rem = divmod(total_seconds, 3600)
    m, _ = divmod(rem, 60)
    return f"{h}h{m:02d}m"


def _fmt_relative_time(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    now = datetime.now(timezone.utc)
    delta = (now - dt).total_seconds()
    if delta < 60:
        return f"{int(delta)}s atrás"
    if delta < 3600:
        return f"{int(delta // 60)}m atrás"
    if delta < 86400:
        return f"{int(delta // 3600)}h atrás"
    return f"{int(delta // 86400)}d atrás"


def _aggregates_table(
    title: str,
    aggs: list[Aggregate],
    label_header: str,
    *,
    show_sessions: bool = True,
) -> Table:
    """Tabela genérica de Aggregate.

    ``show_sessions=False`` esconde a coluna ``sessões`` — usado na tabela
    "Por sessão" porque o agrupamento é 1:1 (sempre 1).
    """
    table = Table(title=title, expand=False, header_style="bold")
    table.add_column(label_header)
    table.add_column("créditos", justify="right")
    table.add_column("turns", justify="right")
    if show_sessions:
        table.add_column("sessões", justify="right")
    table.add_column("duração", justify="right")
    table.add_column("tools", justify="right")
    for a in aggs:
        row = [a.label, _fmt_credits(a.credits), str(a.turns)]
        if show_sessions:
            row.append(str(a.sessions))
        row.extend([_fmt_duration(a.duration), str(a.tool_uses)])
        table.add_row(*row)
    return table


def _agent_pair_table(aggs: list["AgentPairAgg"]) -> Table:
    """Tabela 5 colunas: runtime + persona + métricas (Wave 3 hotfix v0.4.1).

    Distingue runtime engine (kiro_default/auto) da persona configurada
    (nyx/iris/kiro_default), evitando ambiguidade quando todos os turns
    rodam em ``kiro_default`` mas em sessões com personas diferentes.
    """
    table = Table(title="Por agent (runtime × persona)", expand=False, header_style="bold")
    table.add_column("runtime")
    table.add_column("persona")
    table.add_column("créditos", justify="right")
    table.add_column("turns", justify="right")
    table.add_column("sessões", justify="right")
    table.add_column("duração", justify="right")
    table.add_column("tools", justify="right")
    for a in aggs:
        table.add_row(
            a.runtime,
            a.persona,
            _fmt_credits(a.credits),
            str(a.turns),
            str(a.sessions),
            _fmt_duration(a.duration),
            str(a.tool_uses),
        )
    return table


# ─── grupo principal ──────────────────────────────────────────────────────


@click.group(invoke_without_command=True)
@click.option("--version", "show_version", is_flag=True, help="Mostra versão e sai.")
@click.pass_context
def main(ctx: click.Context, show_version: bool) -> None:
    """kiro-dash — painel local de uso e créditos do Kiro CLI."""
    if show_version:
        click.echo(f"kiro-dash {__version__}")
        ctx.exit(0)
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# ─── whoami ──────────────────────────────────────────────────────────────


@main.command()
def whoami() -> None:
    """Identidade AWS, profile do Kiro e billing tier."""
    info = run_whoami()
    if info is None:
        console.print("[red]kiro-cli whoami falhou ou kiro-cli não está no PATH.[/red]")
        raise SystemExit(1)

    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(style="dim")
    table.add_column()

    table.add_row("Tipo de conta", info.account_type or "?")
    table.add_row("E-mail", info.email or "—")
    table.add_row("Região (SSO)", info.region or "—")
    table.add_row("Start URL", info.start_url or "—")
    table.add_row("Profile", info.profile_name or "—")
    if info.profile_arn:
        table.add_row("Profile ARN", info.profile_arn)
        if info.aws_account_id:
            table.add_row("AWS Account", info.aws_account_id)
        if info.profile_region:
            table.add_row("Região (serviço)", info.profile_region)

    title = "Identidade Kiro CLI"
    if info.is_enterprise:
        title += " (enterprise)"
    console.print(Panel(table, title=title, expand=False))

    # Painel de fontes detectadas (Wave 6 — ADR-0001 ; T4-W8 vira tabela rich)
    sources = Sources.detect()
    sources_table = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
    sources_table.add_column("source", style="bold")
    sources_table.add_column("status", justify="center")
    sources_table.add_column("descrição", overflow="fold")
    for slug, symbol, color, detail in sources.summary_rows():
        sources_table.add_row(
            slug,
            Text(symbol, style=color),
            Text(detail, style="dim" if symbol == "—" else "default"),
        )
    console.print(
        Panel(sources_table, title="Fontes detectadas", expand=False)
    )


def _render_snapshot(snap: dict, *, agent: str | None = None) -> None:
    """Renderiza snapshot JSON no mesmo formato visual do today."""
    totals = snap["totals"]
    d = snap["local_date"]

    header = Text()
    header.append(f"{d}  ", style="bold")
    header.append(f"{_fmt_credits(totals['credits'])} créditos  ", style="bold green")
    header.append(f"{totals['turns']} turns em {totals['sessions']} sessões")
    header.append("  [snapshot]", style="dim")
    console.print(Panel(header, title="Histórico", expand=False))
    console.print()

    if snap.get("by_model"):
        table = Table(title="Por modelo", expand=False, header_style="bold")
        for col in ("modelo", "créditos", "turns", "sessões", "duração", "tools"):
            table.add_column(col, justify="right" if col != "modelo" else "left")
        for m in snap["by_model"]:
            table.add_row(
                m["label"], _fmt_credits(m["credits"]), str(m["turns"]),
                str(m["sessions"]), _fmt_duration(timedelta(seconds=m.get("duration_secs", 0))),
                str(m.get("tool_uses", 0)),
            )
        console.print(table)

    if snap.get("by_project"):
        table = Table(title="Por projeto", expand=False, header_style="bold")
        for col in ("projeto", "créditos", "turns", "sessões"):
            table.add_column(col, justify="right" if col != "projeto" else "left")
        for p in snap["by_project"]:
            table.add_row(p["label"], _fmt_credits(p["credits"]),
                          str(p["turns"]), str(p["sessions"]))
        console.print(table)


# ─── today ───────────────────────────────────────────────────────────────


@main.command()
@click.option(
    "--day",
    "day_str",
    default=None,
    help="Dia em formato YYYY-MM-DD (default: hoje, local).",
)
@click.option("--agent", default=None, help="Filtra por agent_name.")
def today(day_str: str | None, agent: str | None) -> None:
    """Agregado de créditos do dia corrente."""
    _ensure_snapshots_silently()
    d = date.fromisoformat(day_str) if day_str else datetime.now().astimezone().date()
    today_local = datetime.now().astimezone().date()

    # D-2 e anterior: lê snapshot
    if d <= today_local - timedelta(days=2):
        from kiro_dash.snapshots import read_snapshot

        snap = read_snapshot(d)
        if snap is None:
            console.print(
                f"[yellow]Sem snapshot para {d}. Tente: kiro-dash snapshot {d}[/yellow]"
            )
            return
        _render_snapshot(snap, agent=agent)
        return

    # D ou D-1: path stateless (live)
    sessions = collect_sessions("all")
    pairs = filter_by_agent(turns_in_local_day(sessions, d), agent)

    if not pairs:
        hint = ""
        if agent is not None:
            hint = f"\n[dim]Filtro --agent {agent} ativo; remova-o para incluir todos os agents.[/dim]"
        console.print(
            f"[yellow]Nenhum turn registrado em {d.isoformat()} (local).[/yellow]"
            f"{hint}"
        )
        return

    total = total_credits(pairs)
    n_sessions = len({s.session_id for s, _ in pairs})

    header = Text()
    header.append(f"{d.isoformat()}  ", style="bold")
    header.append(f"{_fmt_credits(total)} créditos  ", style="bold green")
    header.append(f"{len(pairs)} turns em {n_sessions} sessões")
    console.print(Panel(header, title="Hoje", expand=False))

    # Contexto do ciclo (plano + saldo)
    p = load_plan(default_config_path())
    bal = balance_in_cycle(sessions, p.cycle_start, monthly_credits=p.monthly_credits)
    ctx_color = _balance_color(bal["pct_used"])
    ctx = Text()
    ctx.append(f"  Ciclo {p.tier}: ", style="dim")
    ctx.append(f"{_fmt_credits(bal['consumed'])} / {bal['monthly_credits']} ", style=ctx_color)
    ctx.append(f"({bal['pct_used']:.1f}%)", style=ctx_color)
    console.print(ctx)
    console.print()

    console.print(_aggregates_table("Por modelo", aggregate_by_model(pairs), "modelo"))
    console.print(_agent_pair_table(aggregate_by_agent_pair(pairs)))
    aliases = load_aliases(default_config_path())
    console.print(_aggregates_table("Por projeto", aggregate_by_project(pairs, aliases=aliases), "projeto"))
    console.print(_aggregates_table("Por sessão", aggregate_by_session(pairs), "sessão", show_sessions=False))


# ─── month / year ────────────────────────────────────────────────────────


def _render_period_summary(s) -> None:
    """Header + breakdowns do PeriodSummary."""
    if s.days_with_data == 0:
        console.print(f"[yellow]Sem snapshots no período {s.period_label}.[/yellow]")
        return
    header = Text()
    header.append(f"{s.period_label}  ", style="bold")
    header.append(f"{_fmt_credits(s.credits)} créditos  ", style="bold green")
    header.append(f"{s.turns} turns / {s.sessions} sessões  ")
    header.append(f"({s.days_with_data} dias com dados)", style="dim")
    console.print(Panel(header, title="Resumo", expand=False))

    if s.by_model:
        t = Table(title="Por modelo", expand=False, header_style="bold")
        for col in ("modelo", "créditos", "turns", "sessões"):
            t.add_column(col, justify="right" if col != "modelo" else "left")
        for m in s.by_model:
            t.add_row(m["label"], _fmt_credits(m["credits"]),
                      str(m["turns"]), str(m["sessions"]))
        console.print(t)

    if s.by_project:
        t = Table(title="Por projeto", expand=False, header_style="bold")
        for col in ("projeto", "créditos", "turns", "sessões"):
            t.add_column(col, justify="right" if col != "projeto" else "left")
        for p in s.by_project:
            t.add_row(p["label"], _fmt_credits(p["credits"]),
                      str(p["turns"]), str(p["sessions"]))
        console.print(t)


@main.command()
@click.argument("month_str", required=False)
def month(month_str: str | None) -> None:
    """Resumo mensal de uso (lê snapshots). Formato: YYYY-MM."""
    from kiro_dash.history import month_summary

    if month_str is None:
        t = datetime.now().astimezone().date()
        year, m = t.year, t.month
    else:
        try:
            year, m = map(int, month_str.split("-"))
        except (ValueError, AttributeError):
            console.print(f"[red]Formato inválido: '{month_str}'. Use YYYY-MM.[/red]")
            raise SystemExit(2)
        if not (1 <= m <= 12):
            console.print(f"[red]Mês inválido: {m}.[/red]")
            raise SystemExit(2)

    summary = month_summary(year, m)
    _render_period_summary(summary)


@main.command()
@click.argument("year_str", required=False)
def year(year_str: str | None) -> None:
    """Resumo anual de uso (lê snapshots). Formato: YYYY."""
    from kiro_dash.history import year_summary

    if year_str is None:
        y = datetime.now().astimezone().year
    else:
        try:
            y = int(year_str)
        except ValueError:
            console.print(f"[red]Ano inválido: '{year_str}'.[/red]")
            raise SystemExit(2)

    summary = year_summary(y)
    _render_period_summary(summary)


# ─── compare ─────────────────────────────────────────────────────────────


@main.command()
@click.argument("a_str")
@click.argument("b_str")
def compare(a_str: str, b_str: str) -> None:
    """Compara dois períodos. Aceita YYYY, YYYY-MM, today/yesterday/week/last-week/month/last-month/year/last-year."""
    from kiro_dash.history import diff_summaries, resolve_period

    a = resolve_period(a_str)
    b = resolve_period(b_str)
    if a is None or b is None:
        console.print(
            "[red]Período inválido. Use YYYY, YYYY-MM, "
            "today/yesterday/week/last-week/month/last-month/year/last-year.[/red]"
        )
        raise SystemExit(2)

    diff = diff_summaries(a, b)
    table = Table(
        title=f"{a.period_label} vs {b.period_label}",
        expand=False, header_style="bold",
    )
    table.add_column("métrica")
    table.add_column(a.period_label, justify="right")
    table.add_column(b.period_label, justify="right")
    table.add_column("Δ", justify="right")
    table.add_column("%", justify="right")

    for name, fa, fb, fd in [
        ("créditos", a.credits, b.credits, diff["credits_delta"]),
        ("turns", a.turns, b.turns, diff["turns_delta"]),
        ("sessões", a.sessions, b.sessions, diff["sessions_delta"]),
    ]:
        pct_str = f"{(fd / fb) * 100:+.1f}%" if fb else "—"
        delta_style = "green" if fd >= 0 else "red"
        table.add_row(
            name, _fmt_credits(fa) if isinstance(fa, float) else str(fa),
            _fmt_credits(fb) if isinstance(fb, float) else str(fb),
            Text(f"{fd:+.2f}" if isinstance(fd, float) else f"{fd:+}", style=delta_style),
            pct_str,
        )
    console.print(table)


# ─── session ─────────────────────────────────────────────────────────────


@main.command()
@click.argument("session_id_prefix")
@click.option(
    "--source",
    default="auto",
    type=click.Choice(["cli", "ide", "auto"]),
    help="Fonte: cli, ide ou auto (default — tenta ambos).",
)
def session(session_id_prefix: str, source: str) -> None:
    """Drill-down de uma sessão por prefixo de session_id.

    Se ``--source=auto`` (default), tenta resolver em ambas as fontes
    e relata ambiguidade. ``--source=cli`` força o backend CLI;
    ``--source=ide`` força o backend IDE.
    """
    s: Session | None = None
    cli_match: Session | None = None
    ide_match: Session | None = None

    if source in ("cli", "auto"):
        path = find_session_by_prefix(session_id_prefix)
        if path is not None:
            cli_match = load_session_file(path)

    if source in ("ide", "auto"):
        ide_match = _find_session_by_prefix_in_ide(session_id_prefix)

    if source == "cli":
        s = cli_match
    elif source == "ide":
        s = ide_match
    else:  # auto
        if cli_match and ide_match:
            console.print(
                f"[red]Prefixo '{session_id_prefix}' ambíguo — match em CLI E IDE."
                f"[/red]\n"
                f"  CLI: {cli_match.session_id[:8]}  ({cli_match.title or '—'})\n"
                f"  IDE: {ide_match.session_id}  ({ide_match.title or '—'})\n"
                f"[dim]Use --source cli ou --source ide para desambiguar.[/dim]"
            )
            raise SystemExit(1)
        s = cli_match or ide_match

    if s is None:
        console.print(
            f"[red]Sessão '{session_id_prefix}' não encontrada ou prefixo ambíguo.[/red]\n"
            "[dim]Use 'kiro-dash recent --source all' para listar sessões disponíveis.\n"
            "Tente um prefixo mais longo (8+ chars) se ambíguo.[/dim]"
        )
        raise SystemExit(1)

    # Cabeçalho
    header = Table(show_header=False, box=None, padding=(0, 1))
    header.add_column(style="dim")
    header.add_column()

    header.add_row("Session ID", s.session_id)
    header.add_row("Título", s.title or "—")
    header.add_row("Agent", s.agent_name or "?")
    header.add_row("Modelo", f"{s.model_id} (×{s.rate_multiplier})")
    header.add_row("Context window", f"{s.context_window_tokens:,} tokens")
    header.add_row("Projeto", s.cwd or "—")
    header.add_row("Criada em", s.created_at.astimezone().isoformat(timespec="seconds"))
    header.add_row("Atualizada em", s.updated_at.astimezone().isoformat(timespec="seconds"))
    header.add_row("Ativa", "sim" if s.is_active else "não")
    if s.session_created_reason:
        header.add_row("Origem", s.session_created_reason)

    title = f"Sessão {s.session_id[:8]}"
    if s.is_active:
        title += " ●"
    console.print(Panel(header, title=title, expand=False))

    # Resumo
    summary = Text()
    summary.append(f"{_fmt_credits(s.total_credits)} créditos  ", style="bold green")
    summary.append(f"{len(s.turns)} turns  ")
    summary.append(f"duração total {_fmt_duration(s.total_duration)}  ")
    summary.append(f"tools={s.total_tool_uses}  ")
    summary.append(f"último contexto {s.last_context_usage_pct:.1f}%")
    console.print(summary)
    console.print()

    # Tabela de turns
    if not s.turns:
        console.print("[yellow]Sessão sem turns.[/yellow]")
        return

    table = Table(title="Turns", expand=False, header_style="bold")
    table.add_column("#", justify="right")
    table.add_column("timestamp")
    table.add_column("agent")
    table.add_column("dur", justify="right")
    table.add_column("créditos", justify="right")
    table.add_column("ctx %", justify="right")
    table.add_column("tools", justify="right")
    table.add_column("ciclos", justify="right")
    table.add_column("end_reason")

    for i, t in enumerate(s.turns, start=1):
        if t.end_timestamp is None:
            # Turn em curso (IDE running): sem timestamp final
            ts_str = "● running"
        else:
            ts_str = t.end_timestamp.astimezone().strftime("%H:%M:%S")
        table.add_row(
            str(i),
            ts_str,
            t.agent_name or "?",
            _fmt_duration(t.duration),
            _fmt_credits(t.credits),
            f"{t.context_usage_pct:.1f}",
            str(t.builtin_tool_uses),
            str(t.number_of_cycles),
            t.end_reason,
        )

    console.print(table)


# ─── now (live view) ─────────────────────────────────────────────────────


def _build_now_view(sessions: list[Session]) -> Panel:
    """Renderiza um Panel com sessões ativas + linha de pico do dia."""
    actives = active_sessions(sessions)

    # Painel topo: contagem + créditos do dia
    today_pairs = turns_in_local_day(sessions)
    today_total = total_credits(today_pairs)

    header = Text()
    header.append("kiro-dash now  ", style="bold")
    header.append(f"{len(actives)} sessões ativas  ", style="cyan")
    header.append(f"hoje: {_fmt_credits(today_total)} créditos  ", style="green")
    header.append(datetime.now().astimezone().strftime("(%H:%M:%S)"), style="dim")

    if not actives:
        return Panel(
            Text.from_markup(
                "[dim]Nenhuma sessão ativa no momento.\n"
                "(uma sessão é considerada ativa quando há um arquivo .lock "
                "ao lado do .json em ~/.kiro/sessions/cli/)[/dim]"
            ),
            title=header,
            expand=False,
        )

    table = Table(expand=True, header_style="bold")
    table.add_column("sid", no_wrap=True)
    table.add_column("agent")
    table.add_column("modelo")
    table.add_column("projeto")
    table.add_column("turns", justify="right")
    table.add_column("créditos", justify="right")
    table.add_column("ctx %", justify="right")
    table.add_column("último turn")

    actives.sort(key=lambda s: s.last_turn_at or s.updated_at, reverse=True)
    for s in actives:
        ctx_pct = s.last_context_usage_pct
        ctx_style = "red" if ctx_pct > 80 else "yellow" if ctx_pct > 50 else "white"
        table.add_row(
            s.session_id[:8],
            s.agent_name or "?",
            s.model_id,
            s.cwd or "—",
            str(len(s.turns)),
            _fmt_credits(s.total_credits),
            Text(f"{ctx_pct:.1f}", style=ctx_style),
            _fmt_relative_time(s.last_turn_at or s.updated_at),
        )

    return Panel(table, title=header, expand=True)


@main.command()
@click.option(
    "--refresh",
    default=2.0,
    type=float,
    help="Intervalo de refresh em segundos (default 2.0).",
)
def now(refresh: float) -> None:
    """Live view das sessões ativas. Ctrl+C para sair."""
    if not DEFAULT_SESSIONS_DIR.is_dir():
        console.print(
            f"[red]Diretório de sessões não encontrado: {DEFAULT_SESSIONS_DIR}[/red]"
        )
        raise SystemExit(1)

    try:
        with Live(
            _build_now_view(load_all_sessions()),
            console=console,
            refresh_per_second=max(1.0, 1.0 / refresh),
            screen=False,
        ) as live:
            while True:
                time.sleep(refresh)
                live.update(_build_now_view(load_all_sessions()))
    except KeyboardInterrupt:
        console.print()
        return


# ─── projects ─────────────────────────────────────────────────────────────


@main.command()
@click.option(
    "--window",
    default="week",
    help="Janela: today | week | month | cycle | all | <int dias> (default 'week').",
)
@click.option("--days", default=None, type=int, help="(legacy) override em dias.")
@click.option("--limit", default=10, type=int, help="Top N (default 10).")
@click.option("--agent", default=None, help="Filtra por agent_name.")
def projects(window: str, days: int | None, limit: int, agent: str | None) -> None:
    """Top projetos (heurística) por créditos numa janela nomeada ou em N dias."""
    _ensure_snapshots_silently()
    sessions = collect_sessions("all")
    plan_cfg = load_plan(default_config_path())
    try:
        if days is not None:
            pairs = turns_in_last_days(sessions, days=days)
            window_label = f"últimos {days}d"
        else:
            pairs = resolve_window(sessions, window, cycle_start=plan_cfg.cycle_start)
            window_label = f"janela={window}"
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(2)

    pairs = filter_by_agent(pairs, agent)

    if not pairs:
        console.print(f"[yellow]Sem turns na janela ({window_label}).[/yellow]")
        return

    aggs = aggregate_by_project(pairs, aliases=load_aliases(default_config_path()))[:limit]
    total = total_credits(pairs)

    header = Text()
    header.append(f"{window_label}  ", style="bold")
    header.append(f"{_fmt_credits(total)} créditos", style="bold green")
    console.print(Panel(header, title="Projetos", expand=False))
    console.print(_aggregates_table("Por projeto", aggs, "projeto"))


# ─── models ───────────────────────────────────────────────────────────────


@main.command()
@click.option(
    "--window",
    default="week",
    help="Janela: today | week | month | cycle | all | <int dias> (default 'week').",
)
@click.option("--days", default=None, type=int, help="(legacy) override em dias.")
@click.option("--limit", default=10, type=int, help="Top N (default 10).")
@click.option("--agent", default=None, help="Filtra por agent_name.")
def models(window: str, days: int | None, limit: int, agent: str | None) -> None:
    """Top modelos por créditos numa janela nomeada ou em N dias."""
    _ensure_snapshots_silently()
    sessions = collect_sessions("all")
    plan_cfg = load_plan(default_config_path())
    try:
        if days is not None:
            pairs = turns_in_last_days(sessions, days=days)
            window_label = f"últimos {days}d"
        else:
            pairs = resolve_window(sessions, window, cycle_start=plan_cfg.cycle_start)
            window_label = f"janela={window}"
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(2)

    pairs = filter_by_agent(pairs, agent)

    if not pairs:
        console.print(f"[yellow]Sem turns na janela ({window_label}).[/yellow]")
        return

    aggs = aggregate_by_model(pairs)[:limit]
    total = total_credits(pairs)

    header = Text()
    header.append(f"{window_label}  ", style="bold")
    header.append(f"{_fmt_credits(total)} créditos", style="bold green")
    console.print(Panel(header, title="Modelos", expand=False))
    console.print(_aggregates_table("Por modelo", aggs, "modelo"))


# ─── recent ───────────────────────────────────────────────────────────────


@main.command()
@click.option("--limit", default=20, type=int, help="N últimas sessões (default 20).")
@click.option("--agent", default=None, help="Filtra por agent_name.")
@click.option(
    "--source",
    default="all",
    type=click.Choice(SOURCE_CHOICES),
    help="Fonte de sessões: all (default — CLI+IDE), cli, ou ide.",
)
@click.option(
    "--show-source",
    is_flag=True,
    default=False,
    help="Mostra coluna source no output (auto-on quando --source all).",
)
def recent(
    limit: int, agent: str | None, source: str, show_source: bool
) -> None:
    """Últimas N sessões ordenadas por updated_at desc, ativas marcadas com ●."""
    sessions = _collect_sessions_by_source(source)
    if agent is not None:
        sessions = [s for s in sessions if s.agent_name == agent]
    if not sessions:
        hint = ""
        if source == "cli":
            hint = "\n[dim]Tente --source all para incluir IDE, ou rode `kiro-cli chat` para criar sua primeira sessão.[/dim]"
        elif source == "ide":
            hint = "\n[dim]Abra o Kiro IDE e tenha uma conversa para popular as sessões. Sem IDE? Use --source cli.[/dim]"
        else:
            hint = "\n[dim]Nenhuma sessão em CLI nem IDE. Rode `kiro-cli chat` ou abra o Kiro IDE.[/dim]"
        if agent is not None:
            hint = f"\n[dim]Filtro --agent {agent} pode ser muito restrito; remova-o para ver todas.[/dim]" + hint
        console.print(f"[yellow]Nenhuma sessão encontrada.[/yellow]{hint}")
        return

    sessions = sorted(sessions, key=lambda s: s.updated_at, reverse=True)[:limit]

    show_source_col = show_source or source == "all"
    title_suffix = f" (source={source})" if source != "cli" else ""
    table = Table(
        title=f"Últimas {len(sessions)} sessões{title_suffix}",
        expand=False,
        header_style="bold",
    )
    table.add_column("sid")
    if show_source_col:
        table.add_column("source")
    table.add_column("título", overflow="fold")
    table.add_column("agent")
    table.add_column("modelo")
    table.add_column("turns", justify="right")
    table.add_column("créditos", justify="right")
    table.add_column("atualizada")

    for s in sessions:
        # sid composto vem como 'ide-sessions:5e551001...'; raw 8 chars
        raw_id = s.session_id.split(":", 1)[-1]
        sid = f"{raw_id[:8]}{' ●' if s.is_active else ''}"
        source_label = "ide" if ":" in s.session_id else "cli"
        title = (s.title or "—")[:60]
        row = [sid]
        if show_source_col:
            row.append(source_label)
        row.extend(
            [
                title,
                s.agent_name or "?",
                s.model_id,
                str(len(s.turns)),
                _fmt_credits(s.total_credits),
                _fmt_relative_time(s.updated_at),
            ]
        )
        table.add_row(*row)

    console.print(table)


# ─── tools ────────────────────────────────────────────────────────────────


@main.command()
@click.option("--hours", default=24, type=int, help="Janela em horas (default 24).")
@click.option("--limit", default=20, type=int, help="Top N tools (default 20).")
def tools(hours: int, limit: int) -> None:
    """Breakdown de tool calls nas últimas N horas.

    Em v0.7.0+ inclui CLI (transcripts ``.jsonl``) **e** IDE
    (``execution.usage_summary[].usedTools``). Para forçar só CLI,
    desabilite o IDE com ``KIRO_DASH_NO_IDE_SESSIONS=1``.
    """
    from kiro_dash.aggregator import aggregate_tools_in_window_combined
    from kiro_dash.visual import bar_inline

    aggs = aggregate_tools_in_window_combined(DEFAULT_SESSIONS_DIR, hours=hours)
    if not aggs:
        console.print(
            f"[yellow]Nenhuma tool call nas últimas {hours}h.[/yellow]\n"
            "[dim]Tools são extraídas de transcripts CLI (.jsonl) e de "
            "execution.usageSummary do IDE. Aumente --hours ou tenha uma "
            "sessão com Autopilot que execute tools.[/dim]"
        )
        return

    aggs = aggs[:limit]
    total = sum(a["count"] for a in aggs)
    err_total = sum(a["errors"] for a in aggs)

    header = Text()
    header.append(f"últimas {hours}h  ", style="bold")
    header.append(f"{total} chamadas", style="bold cyan")
    if err_total:
        header.append(f"  {err_total} erros", style="bold red")
    console.print(Panel(header, title="Tools", expand=False))

    table = Table(title="Tools", expand=False, header_style="bold")
    table.add_column("tool")
    table.add_column("count", justify="right")
    table.add_column("share")
    table.add_column("sessões", justify="right")
    table.add_column("erros", justify="right")
    for a in aggs:
        pct = a["count"] / total if total else 0
        bar = f"{bar_inline(pct, width=15)} {pct*100:5.1f}%"
        err_cell = Text(str(a["errors"]), style="red") if a["errors"] else Text("0", style="dim")
        table.add_row(a["name"], str(a["count"]), bar, str(a["sessions"]), err_cell)
    console.print(table)


# ─── sync ─────────────────────────────────────────────────────────────────

_DEFAULT_REMOTE = "gdrive-pessoal"
_DEFAULT_REMOTE_PATH = "kiro-dash/sessions"


def _ensure_rclone(remote: str) -> SyncConfig | None:
    """Verifica binário e remote; mensagens de erro coerentes."""
    if not rclone_available():
        console.print(
            "[red]rclone não está no PATH.[/red] Instale: "
            "`sudo apt install rclone` ou veja https://rclone.org/install/"
        )
        return None
    if not rclone_remote_exists(remote):
        console.print(
            f"[red]Remote rclone '{remote}' não configurado.[/red] "
            f"Rode: rclone config (criar remote tipo 'drive')."
        )
        return None
    return SyncConfig(remote=remote, remote_path=_DEFAULT_REMOTE_PATH)


@main.group()
def sync() -> None:
    """Sincronização de sessões com Google Drive (padrão Iris)."""


@sync.command("push")
@click.option("--remote", default=_DEFAULT_REMOTE, help="Nome do remote rclone.")
@click.option(
    "--include-ide",
    is_flag=True,
    default=False,
    help=(
        "Inclui sessões do Kiro IDE no push (redatadas — sem conteúdo "
        "de mensagens; ver privacidade no README). Default off."
    ),
)
def sync_push_cmd(remote: str, include_ide: bool) -> None:
    """Envia .json locais para o Drive (aditivo, não-destrutivo).

    Por default sincroniza apenas ``~/.kiro/sessions/cli/``. Com
    ``--include-ide``, também envia
    ``~/.config/Kiro/User/globalStorage/kiro.kiroagent/workspace-sessions/``
    redatado (history.message, actions.input/output, rawInput,
    editorState filtrados).
    """
    cfg = _ensure_rclone(remote)
    if cfg is None:
        raise SystemExit(1)
    console.print(f"[dim]Enviando {DEFAULT_SESSIONS_DIR} → {cfg.remote_uri}…[/dim]")
    ok, err = sync_push(cfg, DEFAULT_SESSIONS_DIR)
    if not ok:
        console.print(f"[red]Falha CLI: {err}[/red]")
        raise SystemExit(1)
    console.print("[green]Push CLI concluído.[/green]")

    if include_ide:
        from kiro_dash.backends.ide_sessions import DEFAULT_IDE_SESSIONS_ROOT
        from kiro_dash.sync import sync_push_ide

        ide_root = DEFAULT_IDE_SESSIONS_ROOT
        if not ide_root.is_dir():
            console.print("[yellow]Kiro IDE não detectado; --include-ide ignorado.[/yellow]")
            return
        console.print(f"[dim]Enviando IDE (redatado) → {cfg.remote_uri}/ide-sessions/…[/dim]")
        ok_ide, err_ide = sync_push_ide(cfg, ide_root)
        if not ok_ide:
            console.print(f"[red]Falha IDE: {err_ide}[/red]")
            raise SystemExit(1)
        console.print("[green]Push IDE (redatado) concluído.[/green]")


@sync.command("pull")
@click.option("--remote", default=_DEFAULT_REMOTE, help="Nome do remote rclone.")
def sync_pull_cmd(remote: str) -> None:
    """Baixa .json do Drive para o local (aditivo)."""
    cfg = _ensure_rclone(remote)
    if cfg is None:
        raise SystemExit(1)
    console.print(f"[dim]Baixando {cfg.remote_uri} → {DEFAULT_SESSIONS_DIR}…[/dim]")
    ok, err = sync_pull(cfg, DEFAULT_SESSIONS_DIR)
    if not ok:
        console.print(f"[red]Falha: {err}[/red]")
        raise SystemExit(1)
    console.print("[green]Pull concluído.[/green]")


# ─── plan ─────────────────────────────────────────────────────────────────


@main.group()
def plan() -> None:
    """Gestão do plano declarado (tier, créditos mensais, ciclo)."""


@plan.command("get")
def plan_get() -> None:
    """Mostra o plano atual; inclui dados autoritativos do IDE quando disponíveis."""
    p = load_plan(default_config_path())
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(style="dim")
    table.add_column()
    table.add_row("Tier", p.tier)
    table.add_row("Créditos mensais", str(p.monthly_credits))
    table.add_row("Ciclo iniciado", p.cycle_start.isoformat())
    table.add_row("Config", str(default_config_path()))

    # Auto-detect via IDE
    sources = Sources.detect()
    if sources.ide_state is not None:
        try:
            state = sources.ide_state.read_usage_state()
        except IdeStateError:
            state = None
        if state is not None:
            age = state.age_seconds
            level = freshness_for(age)
            table.add_row("", "")  # separador visual
            table.add_row(
                "Limite servidor (IDE)",
                f"{state.usage_limit:.0f} {state.unit.lower()}",
            )
            if state.overage_cap > 0:
                table.add_row(
                    "Overage cap",
                    f"{state.overage_cap:.0f} @ "
                    f"{state.currency_symbol}{state.overage_rate:.2f}/{state.unit.lower()}",
                )
            table.add_row(
                "Reset em",
                state.reset_date.date().isoformat(),
            )
            table.add_row(
                "Frescor (IDE)",
                Text(
                    f"{format_age(age)} atrás · {level.value}",
                    style=_freshness_color(level),
                ),
            )

    console.print(Panel(table, title="Plano", expand=False))


@plan.command("set")
@click.argument("tier")
@click.option("--credits", "credits_override", type=int, default=None,
              help="Override do default de créditos da tier.")
@click.option("--cycle-start", "cycle_start_str", default=None,
              help="Data de início do ciclo (YYYY-MM-DD).")
def plan_set(tier: str, credits_override: int | None, cycle_start_str: str | None) -> None:
    """Define o plano. Tier deve estar em {free, pro, pro+, power, enterprise}."""
    if tier not in VALID_TIERS:
        console.print(f"[red]tier inválido: '{tier}'. Use um de: {sorted(VALID_TIERS)}.[/red]")
        raise SystemExit(2)

    monthly = credits_override or DEFAULT_MONTHLY_CREDITS[tier]

    if cycle_start_str:
        from datetime import date as _date
        try:
            cycle = _date.fromisoformat(cycle_start_str)
        except ValueError:
            console.print(f"[red]cycle-start inválido: '{cycle_start_str}'. Use YYYY-MM-DD.[/red]")
            raise SystemExit(2)
    else:
        existing = load_plan(default_config_path())
        cycle = existing.cycle_start

    p = PlanConfig(tier=tier, monthly_credits=monthly, cycle_start=cycle)
    save_plan(p, default_config_path())
    console.print(f"[green]Plano salvo:[/green] {p.tier} ({p.monthly_credits} cr/mês), ciclo {p.cycle_start.isoformat()}")


# ─── aliases ──────────────────────────────────────────────────────────────


@main.group()
def aliases() -> None:
    """Gestão de aliases declarativos de projeto."""


@aliases.command("get")
def aliases_get() -> None:
    """Lista aliases atuais."""
    al = load_aliases(default_config_path())
    if not al:
        console.print("[dim]Nenhum alias declarado.[/dim]")
        return
    table = Table(title="Aliases", show_header=True)
    table.add_column("path")
    table.add_column("label")
    for path, label in sorted(al.items()):
        table.add_row(path, label)
    console.print(table)


@aliases.command("set")
@click.argument("path")
@click.argument("label")
def aliases_set(path: str, label: str) -> None:
    """Define alias ``path → label``. Sobrescreve se já existir."""
    al = load_aliases(default_config_path())
    al[path] = label
    save_aliases(al, default_config_path())
    console.print(f"[green]Alias salvo:[/green] {path} → {label}")


@aliases.command("unset")
@click.argument("path")
def aliases_unset(path: str) -> None:
    """Remove alias por path."""
    al = load_aliases(default_config_path())
    if path not in al:
        console.print(f"[yellow]Alias não encontrado: {path}[/yellow]")
        raise SystemExit(1)
    del al[path]
    save_aliases(al, default_config_path())
    console.print(f"[green]Alias removido:[/green] {path}")


# ─── balance ──────────────────────────────────────────────────────────────


def _balance_color(pct: float) -> str:
    if pct >= 95:
        return "red"
    if pct >= 80:
        return "yellow"
    return "green"


def _freshness_color(level: FreshnessLevel) -> str:
    """Mapeia FreshnessLevel para cor rich."""
    return level.value


def _render_balance_from_ide(state, *, sources_summary_hint: bool) -> None:
    """Renderiza saldo autoritativo lido do IDE."""
    age = state.age_seconds
    level = freshness_for(age)
    pct = state.percentage_used
    color = _balance_color(pct)

    # T3-W8: barra wider (40) com tick visual em 80% e 95%
    bar = Text()
    bar_width = 40
    used_blocks = min(bar_width, int(pct / 100.0 * bar_width))
    bar.append("█" * used_blocks, style=color)
    bar.append("░" * (bar_width - used_blocks), style="dim")

    # Tick line — marca 80% e 95% sob a barra
    tick_line = Text()
    pos_80 = int(0.80 * bar_width)
    pos_95 = int(0.95 * bar_width)
    for i in range(bar_width + 1):
        if i == pos_80:
            tick_line.append("│", style="yellow")
        elif i == pos_95:
            tick_line.append("│", style="red")
        elif i == bar_width:
            tick_line.append("┘", style="dim")
        elif i == 0:
            tick_line.append("└", style="dim")
        else:
            tick_line.append(" ")
    tick_label = Text("0%", style="dim")
    tick_label.append(" " * (pos_80 - 2), style="dim")
    tick_label.append("80%", style="yellow")
    tick_label.append(" " * (pos_95 - pos_80 - 3), style="dim")
    tick_label.append("95%", style="red")
    tick_label.append(" " * max(0, bar_width - pos_95 - 3 - 4), style="dim")
    tick_label.append("100%", style="dim")

    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(style="dim")
    table.add_column()
    table.add_row(
        "Consumo",
        f"[b]{state.current_usage:.2f}[/b] / {state.usage_limit:.0f} {state.unit.lower()}",
    )
    table.add_row(
        "Restante",
        f"{state.usage_limit - state.current_usage:.2f}",
    )
    table.add_row("Uso", Text(f"{pct:.2f}%", style=color))
    table.add_row("", bar)
    table.add_row("", tick_line)
    table.add_row("", tick_label)

    # Reset
    days_to_reset = (state.reset_date - datetime.now(timezone.utc)).days
    reset_iso = state.reset_date.date().isoformat()
    if days_to_reset >= 0:
        table.add_row("Reset em", f"{reset_iso} ({days_to_reset}d)")
    else:
        table.add_row("Reset em", reset_iso)

    # Overage com barra dedicada se houver
    if state.current_overages > 0:
        overage_pct = (
            state.current_overages / state.overage_cap * 100.0
            if state.overage_cap > 0
            else 0.0
        )
        overage_bar = Text()
        ow_used = min(20, int(overage_pct / 5))
        overage_bar.append("█" * ow_used, style="red")
        overage_bar.append("░" * (20 - ow_used), style="dim")
        table.add_row(
            "Overage",
            Text(
                f"{state.current_overages:.2f} acima · charges "
                f"{state.currency_symbol}{state.overage_charges:.2f}",
                style="red",
            ),
        )
        table.add_row("", overage_bar)
        table.add_row("", Text(f"cap: {state.overage_cap:.0f}", style="dim"))
    if state.overage_rate > 0 and state.current_overages == 0:
        table.add_row(
            "Overage rate",
            f"{state.currency_symbol}{state.overage_rate:.2f} / {state.unit.lower()}"
            f" (cap {state.overage_cap:.0f})",
        )

    # Frescor
    age_text = format_age(age)
    table.add_row("Fonte", "ide (state.vscdb)")
    table.add_row(
        "Frescor",
        Text(f"{age_text} atrás · {level.value}", style=_freshness_color(level)),
    )
    msg = freshness_message(level, age)
    if msg:
        table.add_row("Aviso", Text(msg, style=_freshness_color(level)))

    title = "Saldo do ciclo (autoritativo)"
    if pct >= 95:
        title += " — ⚠️ próximo do limite"
    elif pct >= 80:
        title += " — atenção"

    console.print(Panel(table, title=title, expand=False))


def _render_balance_from_local_estimate() -> None:
    """Renderiza estimativa local (comportamento pré-Wave 6)."""
    p = load_plan(default_config_path())
    sessions = collect_sessions("all")
    bal = balance_in_cycle(sessions, p.cycle_start, monthly_credits=p.monthly_credits)

    color = _balance_color(bal["pct_used"])
    # T3-W8: bar wider (40) + tick em 80%/95%
    bar = Text()
    bar_width = 40
    used_blocks = min(bar_width, int(bal["pct_used"] / 100.0 * bar_width))
    bar.append("█" * used_blocks, style=color)
    bar.append("░" * (bar_width - used_blocks), style="dim")

    tick_line = Text()
    pos_80 = int(0.80 * bar_width)
    pos_95 = int(0.95 * bar_width)
    for i in range(bar_width + 1):
        if i == pos_80:
            tick_line.append("│", style="yellow")
        elif i == pos_95:
            tick_line.append("│", style="red")
        elif i == bar_width:
            tick_line.append("┘", style="dim")
        elif i == 0:
            tick_line.append("└", style="dim")
        else:
            tick_line.append(" ")
    tick_label = Text("0%", style="dim")
    tick_label.append(" " * (pos_80 - 2), style="dim")
    tick_label.append("80%", style="yellow")
    tick_label.append(" " * (pos_95 - pos_80 - 3), style="dim")
    tick_label.append("95%", style="red")
    tick_label.append(" " * max(0, bar_width - pos_95 - 3 - 4), style="dim")
    tick_label.append("100%", style="dim")

    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(style="dim")
    table.add_column()
    table.add_row("Tier", p.tier)
    table.add_row("Ciclo desde", p.cycle_start.isoformat())
    table.add_row(
        "Consumo",
        f"[b]{_fmt_credits(bal['consumed'])}[/b] / {bal['monthly_credits']} créditos",
    )
    table.add_row("Restante", _fmt_credits(bal["remaining"]))
    table.add_row("Uso", Text(f"{bal['pct_used']:.1f}%", style=color))
    table.add_row("", bar)
    table.add_row("", tick_line)
    table.add_row("", tick_label)
    table.add_row("Turns no ciclo", str(bal["turns"]))
    table.add_row("Sessões no ciclo", str(bal["sessions"]))
    table.add_row("Fonte", "estimativa local (cli)")

    title = "Saldo do ciclo (estimativa)"
    if bal["pct_used"] >= 95:
        title += " — ⚠️ próximo do limite"
    elif bal["pct_used"] >= 80:
        title += " — atenção"

    console.print(Panel(table, title=title, expand=False))


@main.command()
@click.option(
    "--no-ide",
    is_flag=True,
    default=False,
    help="Ignora billing autoritativo do IDE; força estimativa local.",
)
def balance(no_ide: bool) -> None:
    """Saldo do ciclo corrente.

    Quando o Kiro IDE está instalado e foi aberto recentemente, lê o
    billing autoritativo do servidor via ``state.vscdb``. Caso contrário,
    cai para estimativa local baseada no plano declarado (``plan set``).
    """
    sources = Sources.detect()
    used_ide = False

    if not no_ide and sources.ide_state is not None:
        try:
            state = sources.ide_state.read_usage_state()
        except IdeStateError as e:
            console.print(
                f"[yellow]IDE_STATE_SCHEMA_UNKNOWN:[/yellow] "
                f"schema do `kiro.kiroAgent` não reconhecido ({e}). "
                f"Caindo em estimativa local."
            )
            state = None

        if state is not None:
            _render_balance_from_ide(state, sources_summary_hint=False)
            used_ide = True

    if not used_ide:
        _render_balance_from_local_estimate()
        # Banner apenas quando estamos em estimativa local
        if should_show_ide_banner(has_only_cli=sources.has_only_cli()):
            console.print()
            console.print(format_ide_banner_text())
            mark_ide_banner_shown()


# ─── audit (watchdog) ─────────────────────────────────────────────────────


def _fmt_age(secs: int) -> str:
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m{secs % 60:02d}s"
    return f"{secs // 3600}h{(secs % 3600) // 60:02d}m"


@main.group()
def audit() -> None:
    """Watchdog: sessões em curso, travadas, kill operacional."""


@audit.command("running")
@click.option(
    "--source",
    default="all",
    type=click.Choice(SOURCE_CHOICES),
    help="Fonte de sessões: all (default — CLI+IDE), cli, ou ide.",
)
def audit_running(source: str) -> None:
    """Lista sessões com turn em curso AGORA."""
    runs: list[Session] = []
    if source in ("cli", "all"):
        sessions = load_all_sessions()
        runs.extend(running_sessions(sessions))
    if source in ("ide", "all"):
        srcs = Sources.detect()
        if srcs.ide_sessions is not None:
            ide_running = srcs.ide_sessions.running_sessions()
            runs.extend(ide_running)

    if not runs:
        console.print("[dim]Nenhuma sessão em curso.[/dim]")
        return

    show_source_col = source == "all"
    title_suffix = f" (source={source})" if source != "cli" else ""
    table = Table(title=f"Sessões em curso{title_suffix}", show_header=True)
    cols = [
        ("sid", "left"),
    ]
    if show_source_col:
        cols.append(("source", "left"))
    cols.extend(
        [
            ("agent", "left"),
            ("modelo", "left"),
            ("cwd", "left"),
            ("turns", "right"),
            ("idade", "right"),
            ("PID", "right"),
        ]
    )
    for col, justify in cols:
        table.add_column(col, justify=justify)

    now = datetime.now(timezone.utc)
    for s in runs:
        is_ide = ":" in s.session_id
        raw_id = s.session_id.split(":", 1)[-1]
        if is_ide:
            # Sem PID/lock no IDE; usar updated_at como age proxy
            pid_str = "—"
            secs = int((now - s.updated_at).total_seconds())
            age_str = _fmt_age(secs)
        else:
            info = read_lock(s.session_id)
            pid_str = str(info.pid) if info else "?"
            age_str = "?"
            if info:
                secs = int((now - info.started_at).total_seconds())
                age_str = _fmt_age(secs)
        row = [raw_id[:8]]
        if show_source_col:
            row.append("ide" if is_ide else "cli")
        row.extend(
            [
                s.agent_name or "?",
                s.model_id,
                s.cwd or "—",
                str(len(s.turns)),
                age_str,
                pid_str,
            ]
        )
        table.add_row(*row)
    console.print(table)


@audit.command("stuck")
@click.option("--threshold", default=600, type=int,
              help="Limite em segundos (default 600 = 10m).")
def audit_stuck(threshold: int) -> None:
    """Lista running cuja idade ultrapassa o threshold."""
    sessions = load_all_sessions()
    stuck = stuck_sessions(sessions, threshold_secs=threshold)
    if not stuck:
        console.print(f"[green]Nenhuma sessão travada (threshold {threshold}s).[/green]")
        return

    table = Table(title=f"Travadas (>{threshold}s)", show_header=True)
    for col in ("sid", "agent", "cwd", "idade", "PID"):
        table.add_column(col)
    now = datetime.now(timezone.utc)
    for s, info in stuck:
        age = int((now - info.started_at).total_seconds())
        table.add_row(
            s.session_id[:8], s.agent_name or "?",
            s.cwd or "—", _fmt_age(age), str(info.pid),
        )
    console.print(table)


@audit.command("kill")
@click.argument("sid_prefix")
@click.option("--all-stuck", is_flag=True, default=False,
              help="Mata todas as sessões travadas (>threshold).")
@click.option("--threshold", default=600, type=int,
              help="Threshold para --all-stuck (default 600s).")
@click.option("--yes", is_flag=True, default=False,
              help="Não pergunta — força SIGTERM (use com --all-stuck).")
def audit_kill(sid_prefix: str, all_stuck: bool, threshold: int, yes: bool) -> None:
    """Mata sessão por prefixo de SID. Pergunta TERM/KILL/cancel."""
    sessions = load_all_sessions()

    if all_stuck:
        stuck = stuck_sessions(sessions, threshold_secs=threshold)
        if not stuck:
            console.print(f"[green]Nenhuma travada > {threshold}s.[/green]")
            return
        console.print(f"[yellow]{len(stuck)} sessões serão terminadas:[/yellow]")
        for s, info in stuck:
            console.print(f"  - {s.session_id[:8]} (PID {info.pid})")
        if not yes:
            confirm = click.prompt(
                "Confirma SIGTERM em todas? [y/N]", default="N",
            ).strip().lower()
            if confirm != "y":
                console.print("[dim]Cancelado.[/dim]")
                return
        for s, info in stuck:
            r = watchdog_kill_session(s.session_id, sig=_signal.SIGTERM)
            _print_kill_result(r)
        return

    # Modo single — sid_prefix
    matches = [s for s in sessions if s.session_id.startswith(sid_prefix)]
    if not matches:
        console.print(f"[red]Sem sessão com prefixo '{sid_prefix}'.[/red]")
        raise SystemExit(1)
    if len(matches) > 1:
        console.print(f"[red]Prefixo ambíguo, casa {len(matches)} sessões.[/red]")
        raise SystemExit(1)

    s = matches[0]
    info = read_lock(s.session_id)
    if info is None:
        console.print(f"[red]Sessão {s.session_id[:8]} não tem lockfile (não está ativa).[/red]")
        raise SystemExit(1)

    age_secs = int((datetime.now(timezone.utc) - info.started_at).total_seconds())

    console.print(Panel(
        f"[bold]{s.session_id}[/bold]\n"
        f"agent: {s.agent_name}  modelo: {s.model_id}\n"
        f"cwd: {s.cwd}\n"
        f"PID: [bold]{info.pid}[/bold]  idade: {_fmt_age(age_secs)}\n"
        f"último turn: {'em curso' if is_session_running(s) else 'finalizado'}",
        title="Sessão", expand=False,
    ))

    console.print(
        "\nComo terminar?\n"
        "  [bold cyan]t[/bold cyan]erm    — SIGTERM (graceful)\n"
        "  [bold red]k[/bold red]ill    — SIGKILL (forçado)\n"
        "  [bold]c[/bold]ancel  — não fazer nada"
    )
    choice = click.prompt("> ", default="c").strip().lower()[:1]

    if choice == "c":
        console.print("[dim]Cancelado.[/dim]")
        return

    sig = _signal.SIGTERM if choice == "t" else _signal.SIGKILL if choice == "k" else None
    if sig is None:
        console.print(f"[red]Resposta inválida: '{choice}'. Use t/k/c.[/red]")
        raise SystemExit(2)

    r = watchdog_kill_session(s.session_id, sig=sig)
    _print_kill_result(r)


def _print_kill_result(r) -> None:
    if r.ok:
        console.print(f"[green]✓[/green] {r.sid[:8]} — {r.signal} enviado pra PID {r.pid}")
    else:
        console.print(f"[red]✗[/red] {r.sid[:8]} — falha: {r.error}")


@audit.command("log")
@click.argument("sid_prefix")
@click.option("--tail", "tail_n", default=20, type=int, help="Últimas N tool calls (default 20).")
def audit_log(sid_prefix: str, tail_n: int) -> None:
    """Tool calls de uma sessão (lê o .jsonl)."""
    paths = discover_sessions()
    matches = [p for p in paths if p.stem.startswith(sid_prefix)]
    if not matches:
        console.print(f"[red]Sem sessão com prefixo '{sid_prefix}'.[/red]")
        raise SystemExit(1)
    if len(matches) > 1:
        console.print(f"[red]Prefixo ambíguo ({len(matches)} sessões).[/red]")
        raise SystemExit(1)

    sid = matches[0].stem
    jsonl = matches[0].with_suffix(".jsonl")
    if not jsonl.exists():
        console.print(f"[yellow]Sessão {sid[:8]} não tem .jsonl.[/yellow]")
        return

    tools = list(iter_tool_calls(jsonl))[-tail_n:]
    if not tools:
        console.print("[dim]Nenhum tool call registrado.[/dim]")
        return

    table = Table(title=f"Últimas {len(tools)} tool calls — {sid[:8]}", show_header=True)
    for col in ("toolUseId", "tool", "status"):
        table.add_column(col)
    for t in tools:
        status = t.status or "?"
        style = "red" if status.lower() == "error" else "green" if status.lower() == "success" else "dim"
        table.add_row(
            t.tool_use_id[:8] if t.tool_use_id else "—",
            t.name or "—",
            f"[{style}]{status}[/{style}]",
        )
    console.print(table)


@audit.command("watch")
@click.option("--interval", default=2.0, type=float, help="Intervalo de refresh em segundos.")
@click.option("--threshold", default=600, type=int)
def audit_watch(interval: float, threshold: int) -> None:
    """Monitor live: running + stuck atualizando a cada N segundos. Ctrl+C sai."""
    try:
        while True:
            console.clear()
            sessions = load_all_sessions()
            runs = running_sessions(sessions)
            stuck = stuck_sessions(sessions, threshold_secs=threshold)
            console.print(
                f"[dim]{datetime.now().astimezone().strftime('%H:%M:%S')}[/dim]  "
                f"running=[bold]{len(runs)}[/bold]  "
                f"stuck=[bold red]{len(stuck)}[/bold red]  "
                f"[dim](Ctrl+C sai)[/dim]"
            )
            console.print()

            if not runs:
                console.print("[dim]Nenhuma sessão em curso.[/dim]")
            else:
                table = Table(show_header=True)
                for col, justify in (
                    ("sid", "left"), ("agent", "left"), ("modelo", "left"),
                    ("cwd", "left"), ("turns", "right"), ("idade", "right"),
                    ("PID", "right"),
                ):
                    table.add_column(col, justify=justify)
                now = datetime.now(timezone.utc)
                for s in runs:
                    info = read_lock(s.session_id)
                    pid_str = str(info.pid) if info else "?"
                    age_str = "?"
                    if info:
                        secs = int((now - info.started_at).total_seconds())
                        age_str = _fmt_age(secs)
                    table.add_row(
                        s.session_id[:8], s.agent_name or "?", s.model_id,
                        s.cwd or "—", str(len(s.turns)), age_str, pid_str,
                    )
                console.print(table)

            if stuck:
                console.print()
                console.print(f"[red bold]⚠️ {len(stuck)} travada(s) > {threshold}s[/red bold]")
                for s, info in stuck:
                    age = int((datetime.now(timezone.utc) - info.started_at).total_seconds())
                    console.print(f"  - [red]{s.session_id[:8]}[/red] PID {info.pid} idade {_fmt_age(age)}")
            time.sleep(interval)
    except KeyboardInterrupt:
        console.print("\n[dim]Encerrado.[/dim]")


# ─── tui ──────────────────────────────────────────────────────────────────


@main.group()
def cache() -> None:
    """Inspeção e limpeza do cache do parser."""


@cache.command("info")
def cache_info_cmd() -> None:
    """Mostra estatísticas do cache."""
    from kiro_dash.cache import cache_info as _cache_info, cache_dir_default

    info = _cache_info()
    table = Table(title="Cache", show_header=True)
    table.add_column("namespace")
    table.add_column("entries", justify="right")
    table.add_column("bytes", justify="right")
    for ns, stats in info.items():
        table.add_row(ns, str(stats["entries"]), str(stats["bytes"]))
    table.add_row("[dim]root[/dim]", "", str(cache_dir_default()))
    console.print(table)


@cache.command("clear")
def cache_clear_cmd() -> None:
    """Remove todas as entradas do cache."""
    from kiro_dash.cache import clear_cache

    out = clear_cache()
    total = sum(out.values())
    console.print(f"[green]Cache limpo:[/green] {total} entradas removidas {out}")


@main.command()
def tui() -> None:
    """Lança a TUI interativa (6 abas: now/today/projects/models/tools/session)."""
    from kiro_dash.views.app import run_app
    raise SystemExit(run_app())


# ─── tool (drill-down) ────────────────────────────────────────────────────


def collect_recent_tools(hours: int = 24) -> list:
    """Tools de todas as sessões nas últimas N horas, ordenadas por session_id."""
    import time as _t
    cutoff = _t.time() - hours * 3600
    out = []
    for path in DEFAULT_SESSIONS_DIR.iterdir():
        if not (path.is_file() and path.suffix == ".jsonl"):
            continue
        try:
            if path.stat().st_mtime < cutoff:
                continue
        except OSError:
            continue
        out.extend(iter_tool_calls(path))
    return out


@main.command()
@click.argument("name")
@click.option("--hours", default=24, type=int, help="Janela em horas (default 24).")
@click.option("--errors-only", is_flag=True, default=False, help="Só status=error.")
@click.option("--tail", default=20, type=int, help="Últimas N chamadas (default 20).")
@click.option("--show-input", is_flag=True, default=False,
              help="Mostra values do input (debug pessoal).")
def tool(name: str, hours: int, errors_only: bool, tail: int, show_input: bool) -> None:
    """Drill-down de uma tool específica."""
    calls = [t for t in collect_recent_tools(hours=hours) if t.name == name]
    if errors_only:
        calls = [t for t in calls if (t.status or "").lower() == "error"]
    calls = calls[:tail]

    if not calls:
        console.print(f"[yellow]Nenhuma chamada de {name!r} nas últimas {hours}h"
                      f"{' (filtro: errors-only)' if errors_only else ''}.[/yellow]")
        return

    n_errors = sum(1 for t in calls if (t.status or "").lower() == "error")
    header = Text()
    header.append(f"{name}  ", style="bold")
    header.append(f"{len(calls)} chamadas  ", style="dim")
    if n_errors:
        header.append(f"{n_errors} erros", style="bold red")
    console.print(Panel(header, title="Tool", expand=False))

    table = Table(show_header=True, header_style="bold")
    table.add_column("status")
    table.add_column("toolUseId")
    table.add_column("input keys")
    table.add_column("error / preview", overflow="fold")
    for t in calls:
        status_cell = Text(t.status or "?",
                           style="red" if (t.status or "").lower() == "error" else "green")
        keys_cell = ", ".join(t.input_keys) if t.input_keys else "—"
        err_cell = Text(t.error_summary or "—",
                        style="red" if t.error_summary else "dim")
        table.add_row(status_cell, t.tool_use_id[:8], keys_cell, err_cell)
    console.print(table)


# ─── snapshot ─────────────────────────────────────────────────────────────

_already_ensured = False


def _ensure_snapshots_silently() -> None:
    """Lazy + self-healing: garante snapshots passados. Silencioso."""
    global _already_ensured  # noqa: PLW0603
    if _already_ensured:
        return
    _already_ensured = True
    try:
        sessions = collect_sessions("all")
        yesterday = datetime.now().astimezone().date() - timedelta(days=1)
        ensure_snapshots_up_to(yesterday, sessions, lookback_days=30)
    except Exception:
        pass


@main.command()
@click.argument("date_str", required=False)
@click.option("--force", is_flag=True, default=False,
              help="Re-escreve snapshot existente.")
def snapshot(date_str: str | None, force: bool) -> None:
    """Gera snapshot histórico.

    Sem argumento: roda lazy/self-healing (últimos 30 dias até ontem).
    Com YYYY-MM-DD: gera/garante esse dia. --force sobrescreve.
    """
    sessions = collect_sessions("all")
    today_d = datetime.now().astimezone().date()

    if date_str is None:
        yesterday = today_d - timedelta(days=1)
        created = ensure_snapshots_up_to(yesterday, sessions)
        if created:
            console.print(f"[green]Criados {len(created)} snapshot(s).[/green]")
            for p in created[-5:]:
                console.print(f"  [dim]{p.name}[/dim]")
        else:
            console.print("[dim]Nenhum snapshot pendente.[/dim]")
        return

    try:
        d = date.fromisoformat(date_str)
    except ValueError:
        console.print(f"[red]Data inválida: '{date_str}'. Use YYYY-MM-DD.[/red]")
        raise SystemExit(2)

    if d >= today_d:
        console.print(f"[yellow]{d} é hoje ou futuro — snapshots só fecham D-1.[/yellow]")
        raise SystemExit(2)

    target = write_snapshot(sessions, d=d, overwrite=force)
    console.print(f"[green]Snapshot garantido:[/green] {target.name}")


if __name__ == "__main__":  # pragma: no cover
    main()
