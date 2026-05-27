"""Servidor MCP stdio de ``kiro-dash``.

Expõe o estado de uso do Kiro CLI como ferramentas consultáveis por
outros agentes. **Cego ao conteúdo de mensagens** — só metadata
estrutural.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from kiro_dash.account import WhoAmI, run_whoami
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
from kiro_dash.backends import Capability
from kiro_dash.backends.ide_state import IdeStateError
from kiro_dash.freshness import freshness_for
from kiro_dash.parser import (
    find_session_by_prefix,
    load_all_sessions,
    load_session_file,
)
from kiro_dash.sources import Sources

# Wave 6 frente Q: tools podem aceitar parâmetro `source` para
# enxergar sessões IDE. Default ``cli`` preserva retro-compat.
VALID_SOURCES = ("cli", "ide", "all", "auto")


def _collect_sessions_for_mcp(source: str = "cli") -> list:
    """Coleta sessões para tools MCP.

    Espelha :func:`kiro_dash.cli._collect_sessions_by_source` mas sem
    importar do CLI (evita ciclo). ``source`` ∈ {cli, ide, all}.
    """
    out: list = []
    if source not in ("cli", "ide", "all"):
        # default seguro: cli
        source = "cli"
    if source in ("cli", "all"):
        out.extend(load_all_sessions())
    if source in ("ide", "all"):
        srcs = Sources.detect()
        if srcs.ide_sessions is not None:
            out.extend(srcs.ide_sessions.list_sessions())
    return out


def _agg_to_dict(a: Aggregate) -> dict:
    return {
        "label": a.label,
        "credits": round(a.credits, 6),
        "turns": a.turns,
        "sessions": a.sessions,
        "duration_seconds": int(a.duration.total_seconds()),
        "tool_uses": a.tool_uses,
    }


def tool_today_summary(*, now: datetime | None = None) -> dict:
    sessions = load_all_sessions()
    pairs = turns_in_local_day(sessions, now=now)
    n = now if now is not None else datetime.now(timezone.utc)
    return {
        "date": n.astimezone().date().isoformat(),
        "total_credits": round(total_credits(pairs), 6),
        "total_turns": len(pairs),
        "total_sessions": len({s.session_id for s, _ in pairs}),
        "by_model": [_agg_to_dict(a) for a in aggregate_by_model(pairs)],
        "by_agent": [_agg_to_dict(a) for a in aggregate_by_agent(pairs)],
        "by_cwd": [_agg_to_dict(a) for a in aggregate_by_cwd(pairs)],
        "by_session": [_agg_to_dict(a) for a in aggregate_by_session(pairs)],
    }


def tool_active_sessions(source: str = "cli") -> list[dict]:
    """Sessões ativas. ``source`` ∈ {cli (default), ide, all}.

    Para IDE: usa ``IdeSessionBackend.running_sessions()`` (heurística
    via ``execution.status=running`` no catálogo, decisão #10 da Q).
    """
    out: list[dict] = []
    if source in ("cli", "all"):
        sessions = load_all_sessions()
        for s in active_sessions(sessions):
            last = s.last_turn_at or s.updated_at
            out.append(
                {
                    "session_id": s.session_id,
                    "source": "cli",
                    "title": s.title,
                    "agent_name": s.agent_name,
                    "model_id": s.model_id,
                    "rate_multiplier": s.rate_multiplier,
                    "cwd": s.cwd,
                    "turns_count": len(s.turns),
                    "total_credits": round(s.total_credits, 6),
                    "context_usage_pct": s.last_context_usage_pct,
                    "last_turn_at": last.isoformat() if last else None,
                }
            )
    if source in ("ide", "all"):
        srcs = Sources.detect()
        if srcs.ide_sessions is not None:
            for s in srcs.ide_sessions.running_sessions():
                last = s.updated_at
                out.append(
                    {
                        "session_id": s.session_id,
                        "source": "ide",
                        "title": s.title,
                        "agent_name": s.agent_name,
                        "model_id": s.model_id,
                        "rate_multiplier": s.rate_multiplier,
                        "cwd": s.cwd,
                        "turns_count": len(s.turns),
                        "total_credits": round(s.total_credits, 6),
                        "context_usage_pct": s.last_context_usage_pct,
                        "last_turn_at": last.isoformat() if last else None,
                    }
                )
    return out


def _find_ide_session_by_prefix(prefix: str):
    """Resolve prefixo de session_id em IDE. Retorna ``Session`` ou ``None``."""
    srcs = Sources.detect()
    if srcs.ide_sessions is None:
        return None
    matches = []
    for s in srcs.ide_sessions.list_sessions():
        composite = s.session_id
        raw = composite.split(":", 1)[-1] if ":" in composite else composite
        if raw.startswith(prefix) or composite.startswith(prefix):
            matches.append(s)
    if len(matches) == 1:
        return matches[0]
    return None


def _session_to_dict(s, source: str) -> dict:
    """Serializa Session (CLI ou IDE) para payload MCP."""
    return {
        "session_id": s.session_id,
        "source": source,
        "title": s.title,
        "agent_name": s.agent_name,
        "model_id": s.model_id,
        "rate_multiplier": s.rate_multiplier,
        "context_window_tokens": s.context_window_tokens,
        "cwd": s.cwd,
        "created_at": s.created_at.isoformat(),
        "updated_at": s.updated_at.isoformat(),
        "is_active": s.is_active,
        "session_created_reason": s.session_created_reason,
        "turns_count": len(s.turns),
        "total_credits": round(s.total_credits, 6),
        "total_duration_seconds": int(s.total_duration.total_seconds()),
        "total_tool_uses": s.total_tool_uses,
        "last_context_usage_pct": s.last_context_usage_pct,
        "turns": [
            {
                "end_timestamp": (
                    t.end_timestamp.isoformat() if t.end_timestamp else None
                ),
                "agent_name": t.agent_name,
                "duration_seconds": int(t.duration.total_seconds()),
                "credits": round(t.credits, 6),
                "context_usage_pct": t.context_usage_pct,
                "builtin_tool_uses": t.builtin_tool_uses,
                "number_of_cycles": t.number_of_cycles,
                "end_reason": t.end_reason,
            }
            for t in s.turns
        ],
    }


def tool_session_details(session_id_prefix: str, source: str = "auto") -> dict | None:
    """Drill-down de sessão por prefix.

    ``source=auto`` (default): tenta CLI primeiro, depois IDE.
    ``source=cli``/``source=ide``: força backend específico. Retorna
    ``None`` se prefix não casa em fonte alguma.
    """
    cli_session = None
    ide_session = None

    if source in ("cli", "auto"):
        path = find_session_by_prefix(session_id_prefix)
        if path is not None:
            cli_session = load_session_file(path)

    if source in ("ide", "auto"):
        ide_session = _find_ide_session_by_prefix(session_id_prefix)

    if source == "cli":
        if cli_session is None:
            return None
        return _session_to_dict(cli_session, "cli")
    if source == "ide":
        if ide_session is None:
            return None
        return _session_to_dict(ide_session, "ide")
    # auto: priorize CLI, mas se ambos casam reportar ambiguidade
    if cli_session and ide_session:
        return {
            "ambiguous": True,
            "matches": [
                _session_to_dict(cli_session, "cli"),
                _session_to_dict(ide_session, "ide"),
            ],
        }
    if cli_session:
        return _session_to_dict(cli_session, "cli")
    if ide_session:
        return _session_to_dict(ide_session, "ide")
    return None


def tool_top_projects(days: int = 7, limit: int = 10, *, now: datetime | None = None) -> list[dict]:
    sessions = load_all_sessions()
    pairs = turns_in_last_days(sessions, days=days, now=now)
    return [_agg_to_dict(a) for a in aggregate_by_cwd(pairs)[:limit]]


def tool_top_models(days: int = 7, limit: int = 10, *, now: datetime | None = None) -> list[dict]:
    sessions = load_all_sessions()
    pairs = turns_in_last_days(sessions, days=days, now=now)
    return [_agg_to_dict(a) for a in aggregate_by_model(pairs)[:limit]]


def tool_account_info() -> dict:
    info = run_whoami()
    if info is None:
        return {"available": False}
    return {
        "available": True,
        "account_type": info.account_type,
        "email": info.email,
        "region_sso": info.region,
        "start_url": info.start_url,
        "profile_name": info.profile_name,
        "profile_arn": info.profile_arn,
        "aws_account_id": info.aws_account_id,
        "profile_region": info.profile_region,
        "is_enterprise": info.is_enterprise,
    }


def tool_usage_state() -> dict:
    """Billing autoritativo do servidor Kiro via Kiro IDE (Wave 6).

    Lê ``kiro.kiroAgent.usageState`` do ``state.vscdb`` do IDE. Retorna
    ``{"available": False, "error": "..."}`` se o IDE não está instalado
    ou se o schema não é reconhecido.
    """
    sources = Sources.detect()
    backends = sources.available_for(Capability.USAGE_STATE)
    if not backends:
        return {
            "available": False,
            "error": "IDE_STATE_UNAVAILABLE",
            "hint": (
                "Kiro IDE não detectado. Instale https://kiro.dev/downloads/ "
                "e abra-o pelo menos uma vez para refresh."
            ),
        }

    backend = backends[0]
    try:
        state = backend.read_usage_state()  # type: ignore[attr-defined]
    except IdeStateError as e:
        return {
            "available": False,
            "error": "IDE_STATE_SCHEMA_UNKNOWN",
            "detail": str(e),
        }

    if state is None:
        return {
            "available": False,
            "error": "IDE_STATE_UNAVAILABLE",
            "hint": "state.vscdb sem chave kiro.kiroAgent",
        }

    age = state.age_seconds
    level = freshness_for(age)
    return {
        "available": True,
        "source": "ide",
        "current_usage": round(state.current_usage, 6),
        "usage_limit": state.usage_limit,
        "percentage_used": round(state.percentage_used, 6),
        "current_overages": state.current_overages,
        "overage_cap": state.overage_cap,
        "overage_charges": state.overage_charges,
        "overage_rate": state.overage_rate,
        "reset_date": state.reset_date.isoformat(),
        "currency_code": state.currency_code,
        "currency_symbol": state.currency_symbol,
        "unit": state.unit,
        "type": state.type,
        "timestamp": state.timestamp.isoformat(),
        "data_age_seconds": round(age, 3),
        "freshness_level": level.value,
        "schema_version_observed": state.schema_version_observed,
    }


def main() -> int:
    """Entry point: sobe o servidor MCP stdio."""
    asyncio.run(_serve())
    return 0


async def _serve() -> None:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import TextContent, Tool

    app = Server("kiro-dash")

    tool_specs = [
        Tool(
            name="today_summary",
            description="Agregado do dia local: créditos, turns, modelos, agents, projetos.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="active_sessions",
            description=(
                "Sessões ativas no momento. CLI usa lockfile; IDE usa "
                "execution.status=running do catálogo. Aceita parâmetro "
                "'source' ∈ {cli (default), ide, all}."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "enum": ["cli", "ide", "all"],
                        "default": "cli",
                        "description": "Fonte de sessões",
                    }
                },
            },
        ),
        Tool(
            name="session_details",
            description=(
                "Drill-down estrutural de uma sessão por prefixo de "
                "session_id. Aceita 'source' ∈ {auto (default — tenta "
                "ambas), cli, ide}."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id_prefix": {"type": "string"},
                    "source": {
                        "type": "string",
                        "enum": ["auto", "cli", "ide"],
                        "default": "auto",
                        "description": "Fonte para resolução do prefix",
                    },
                },
                "required": ["session_id_prefix"],
            },
        ),
        Tool(
            name="account_info",
            description="Identidade AWS / Kiro do dispositivo.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="top_projects",
            description="Top projetos (cwd) por créditos numa janela de N dias.",
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "default": 7},
                    "limit": {"type": "integer", "default": 10},
                },
            },
        ),
        Tool(
            name="top_models",
            description="Top modelos por créditos numa janela de N dias.",
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "default": 7},
                    "limit": {"type": "integer", "default": 10},
                },
            },
        ),
        Tool(
            name="usage_state",
            description=(
                "Billing autoritativo do servidor Kiro via Kiro IDE: "
                "saldo, limite, overage, reset, frescor. Disponível "
                "apenas se Kiro IDE estiver instalado e tiver sido aberto "
                "pelo menos uma vez."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
    ]

    @app.list_tools()
    async def _list_tools() -> list[Tool]:
        return tool_specs

    @app.call_tool()
    async def _call_tool(name: str, arguments: dict) -> list[TextContent]:
        if name == "today_summary":
            payload = tool_today_summary()
        elif name == "active_sessions":
            payload = tool_active_sessions(source=arguments.get("source", "cli"))
        elif name == "session_details":
            payload = tool_session_details(
                arguments.get("session_id_prefix", ""),
                source=arguments.get("source", "auto"),
            )
        elif name == "account_info":
            payload = tool_account_info()
        elif name == "top_projects":
            payload = tool_top_projects(
                days=int(arguments.get("days", 7)),
                limit=int(arguments.get("limit", 10)),
            )
        elif name == "top_models":
            payload = tool_top_models(
                days=int(arguments.get("days", 7)),
                limit=int(arguments.get("limit", 10)),
            )
        elif name == "usage_state":
            payload = tool_usage_state()
        else:
            payload = {"error": f"unknown tool: {name}"}
        return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]

    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    raise SystemExit(main())
