"""CLI ``kiro-dash`` — entry point.

Subcomandos:
    whoami   - identidade AWS / billing / profile do Kiro
    today    - agregado do dia corrente (créditos, modelo, agent, projeto)
    session  - drill-down de uma sessão (por prefixo de session_id)
    now      - live view das sessões ativas
"""
from __future__ import annotations

import time
from datetime import date, datetime, timezone
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
    active_sessions,
    aggregate_by_agent,
    aggregate_by_cwd,
    aggregate_by_model,
    aggregate_by_session,
    total_credits,
    turns_in_last_days,
    turns_in_local_day,
)
from kiro_dash.models import Session
from kiro_dash.parser import (
    DEFAULT_SESSIONS_DIR,
    discover_sessions,
    find_session_by_prefix,
    load_all_sessions,
    load_session_file,
)

console = Console()


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


def _aggregates_table(title: str, aggs: list[Aggregate], label_header: str) -> Table:
    table = Table(title=title, expand=False, header_style="bold")
    table.add_column(label_header)
    table.add_column("créditos", justify="right")
    table.add_column("turns", justify="right")
    table.add_column("sessões", justify="right")
    table.add_column("duração", justify="right")
    table.add_column("tools", justify="right")
    for a in aggs:
        table.add_row(
            a.label,
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


# ─── today ───────────────────────────────────────────────────────────────


@main.command()
@click.option(
    "--day",
    "day_str",
    default=None,
    help="Dia em formato YYYY-MM-DD (default: hoje, local).",
)
def today(day_str: str | None) -> None:
    """Agregado de créditos do dia corrente."""
    d = date.fromisoformat(day_str) if day_str else datetime.now().astimezone().date()

    sessions = load_all_sessions()
    pairs = turns_in_local_day(sessions, d)

    if not pairs:
        console.print(f"[yellow]Nenhum turn registrado em {d.isoformat()} (local).[/yellow]")
        return

    total = total_credits(pairs)
    n_sessions = len({s.session_id for s, _ in pairs})

    header = Text()
    header.append(f"{d.isoformat()}  ", style="bold")
    header.append(f"{_fmt_credits(total)} créditos  ", style="bold green")
    header.append(f"{len(pairs)} turns em {n_sessions} sessões")
    console.print(Panel(header, title="Hoje", expand=False))

    console.print(_aggregates_table("Por modelo", aggregate_by_model(pairs), "modelo"))
    console.print(_aggregates_table("Por agent", aggregate_by_agent(pairs), "agent"))
    console.print(_aggregates_table("Por projeto (cwd)", aggregate_by_cwd(pairs), "cwd"))
    console.print(_aggregates_table("Por sessão", aggregate_by_session(pairs), "sessão"))


# ─── session ─────────────────────────────────────────────────────────────


@main.command()
@click.argument("session_id_prefix")
def session(session_id_prefix: str) -> None:
    """Drill-down de uma sessão por prefixo de session_id."""
    path = find_session_by_prefix(session_id_prefix)
    if path is None:
        console.print(
            f"[red]Sessão '{session_id_prefix}' não encontrada ou prefixo ambíguo.[/red]"
        )
        raise SystemExit(1)

    s = load_session_file(path)
    if s is None:
        console.print(f"[red]Falha ao parsear {path.name}.[/red]")
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
        table.add_row(
            str(i),
            t.end_timestamp.astimezone().strftime("%H:%M:%S"),
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
@click.option("--days", default=7, type=int, help="Janela em dias (default 7).")
@click.option("--limit", default=10, type=int, help="Top N projetos (default 10).")
def projects(days: int, limit: int) -> None:
    """Top projetos (cwd) por créditos consumidos numa janela de N dias."""
    sessions = load_all_sessions()
    pairs = turns_in_last_days(sessions, days=days)
    if not pairs:
        console.print(f"[yellow]Sem turns nos últimos {days} dias.[/yellow]")
        return

    aggs = aggregate_by_cwd(pairs)[:limit]
    total = total_credits(pairs)

    header = Text()
    header.append(f"últimos {days}d  ", style="bold")
    header.append(f"{_fmt_credits(total)} créditos", style="bold green")
    console.print(Panel(header, title="Projetos", expand=False))
    console.print(_aggregates_table("Por projeto (cwd)", aggs, "cwd"))


if __name__ == "__main__":  # pragma: no cover
    main()
