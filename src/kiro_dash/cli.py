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
    aggregate_by_project,
    aggregate_by_session,
    aggregate_tools_in_window,
    balance_in_cycle,
    resolve_window,
    total_credits,
    turns_in_last_days,
    turns_in_local_day,
)
from kiro_dash.config import (
    DEFAULT_MONTHLY_CREDITS,
    VALID_TIERS,
    PlanConfig,
    default_config_path,
    load_plan,
    save_plan,
)
from kiro_dash.models import Session
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
    console.print(_aggregates_table("Por agent", aggregate_by_agent(pairs), "agent"))
    console.print(_aggregates_table("Por projeto", aggregate_by_project(pairs), "projeto"))
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
@click.option(
    "--window",
    default="week",
    help="Janela: today | week | month | cycle | all | <int dias> (default 'week').",
)
@click.option("--days", default=None, type=int, help="(legacy) override em dias.")
@click.option("--limit", default=10, type=int, help="Top N (default 10).")
def projects(window: str, days: int | None, limit: int) -> None:
    """Top projetos (heurística) por créditos numa janela nomeada ou em N dias."""
    sessions = load_all_sessions()
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

    if not pairs:
        console.print(f"[yellow]Sem turns na janela ({window_label}).[/yellow]")
        return

    aggs = aggregate_by_project(pairs)[:limit]
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
def models(window: str, days: int | None, limit: int) -> None:
    """Top modelos por créditos numa janela nomeada ou em N dias."""
    sessions = load_all_sessions()
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
def recent(limit: int) -> None:
    """Últimas N sessões ordenadas por updated_at desc, ativas marcadas com ●."""
    sessions = load_all_sessions()
    if not sessions:
        console.print("[yellow]Nenhuma sessão encontrada.[/yellow]")
        return

    sessions = sorted(sessions, key=lambda s: s.updated_at, reverse=True)[:limit]

    table = Table(title=f"Últimas {len(sessions)} sessões", expand=False, header_style="bold")
    table.add_column("sid")
    table.add_column("título", overflow="fold")
    table.add_column("agent")
    table.add_column("modelo")
    table.add_column("turns", justify="right")
    table.add_column("créditos", justify="right")
    table.add_column("atualizada")

    for s in sessions:
        sid = f"{s.session_id[:8]}{' ●' if s.is_active else ''}"
        title = (s.title or "—")[:60]
        table.add_row(
            sid,
            title,
            s.agent_name or "?",
            s.model_id,
            str(len(s.turns)),
            _fmt_credits(s.total_credits),
            _fmt_relative_time(s.updated_at),
        )

    console.print(table)


# ─── tools ────────────────────────────────────────────────────────────────


@main.command()
@click.option("--hours", default=24, type=int, help="Janela em horas (default 24).")
@click.option("--limit", default=20, type=int, help="Top N tools (default 20).")
def tools(hours: int, limit: int) -> None:
    """Breakdown de tool calls nas últimas N horas (lê .jsonl)."""
    aggs = aggregate_tools_in_window(DEFAULT_SESSIONS_DIR, hours=hours)
    if not aggs:
        console.print(f"[yellow]Nenhuma tool call nas últimas {hours}h.[/yellow]")
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
    table.add_column("sessões", justify="right")
    table.add_column("erros", justify="right")
    for a in aggs:
        err_cell = Text(str(a["errors"]), style="red") if a["errors"] else Text("0", style="dim")
        table.add_row(a["name"], str(a["count"]), str(a["sessions"]), err_cell)
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
def sync_push_cmd(remote: str) -> None:
    """Envia .json locais para o Drive (aditivo, não-destrutivo)."""
    cfg = _ensure_rclone(remote)
    if cfg is None:
        raise SystemExit(1)
    console.print(f"[dim]Enviando {DEFAULT_SESSIONS_DIR} → {cfg.remote_uri}…[/dim]")
    ok, err = sync_push(cfg, DEFAULT_SESSIONS_DIR)
    if not ok:
        console.print(f"[red]Falha: {err}[/red]")
        raise SystemExit(1)
    console.print("[green]Push concluído.[/green]")


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
    """Mostra o plano atual."""
    p = load_plan(default_config_path())
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(style="dim")
    table.add_column()
    table.add_row("Tier", p.tier)
    table.add_row("Créditos mensais", str(p.monthly_credits))
    table.add_row("Ciclo iniciado", p.cycle_start.isoformat())
    table.add_row("Config", str(default_config_path()))
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


# ─── balance ──────────────────────────────────────────────────────────────


def _balance_color(pct: float) -> str:
    if pct >= 95:
        return "red"
    if pct >= 80:
        return "yellow"
    return "green"


@main.command()
def balance() -> None:
    """Saldo estimado do ciclo corrente."""
    p = load_plan(default_config_path())
    sessions = load_all_sessions()
    bal = balance_in_cycle(sessions, p.cycle_start, monthly_credits=p.monthly_credits)

    color = _balance_color(bal["pct_used"])
    bar = Text()
    used_blocks = min(20, int(bal["pct_used"] / 5))
    bar.append("█" * used_blocks, style=color)
    bar.append("░" * (20 - used_blocks), style="dim")

    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(style="dim")
    table.add_column()
    table.add_row("Tier", p.tier)
    table.add_row("Ciclo desde", p.cycle_start.isoformat())
    table.add_row(
        "Consumo",
        f"{_fmt_credits(bal['consumed'])} / {bal['monthly_credits']} créditos",
    )
    table.add_row("Restante", _fmt_credits(bal["remaining"]))
    table.add_row("Uso", Text(f"{bal['pct_used']:.1f}%", style=color))
    table.add_row("Barra", bar)
    table.add_row("Turns no ciclo", str(bal["turns"]))
    table.add_row("Sessões no ciclo", str(bal["sessions"]))

    title = "Saldo do ciclo"
    if bal["pct_used"] >= 95:
        title += " — ⚠️ próximo do limite"
    elif bal["pct_used"] >= 80:
        title += " — atenção"

    console.print(Panel(table, title=title, expand=False))


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
def audit_running() -> None:
    """Lista sessões com turn em curso AGORA."""
    sessions = load_all_sessions()
    runs = running_sessions(sessions)
    if not runs:
        console.print("[dim]Nenhuma sessão em curso.[/dim]")
        return

    table = Table(title="Sessões em curso", show_header=True)
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


# ─── tui ──────────────────────────────────────────────────────────────────


@main.command()
def tui() -> None:
    """Lança a TUI interativa (6 abas: now/today/projects/models/tools/session)."""
    from kiro_dash.views.app import run_app
    raise SystemExit(run_app())


if __name__ == "__main__":  # pragma: no cover
    main()
