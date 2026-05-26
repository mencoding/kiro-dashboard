# Wave 1 / Frente C — MCP server `kiro-dash-mcp` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expor o estado de uso do Kiro CLI como ferramentas consultáveis por outros agentes via Model Context Protocol (MCP), reaproveitando o parser, o aggregator e o module account já existentes.

**Architecture:** Servidor MCP stdio usando o pacote `mcp` oficial. Tools expostas:
- `today_summary` — agregado do dia local
- `active_sessions` — sessões com `.lock`
- `session_details(session_id_prefix)` — drill-down (campos estruturais; nunca conteúdo)
- `account_info` — saída parseada de `kiro-cli whoami`
- `top_projects(days, limit)` — wrapper sobre `aggregate_by_cwd`
- `top_models(days, limit)` — wrapper sobre `aggregate_by_model`

Todas as tools devolvem JSON estruturado (dict ou list[dict]). **Nenhuma expõe conteúdo de mensagens ou `metering_usage` interno bruto** — apenas os campos já públicos via CLI.

**Tech Stack:** Python 3.12, [mcp >= 1.0](https://github.com/modelcontextprotocol/python-sdk), pytest. Reusa código existente.

**Branch:** `feat/wave1-mcp-server`

---

## File Structure

| Arquivo | Responsabilidade | Mudança |
|---|---|---|
| `pyproject.toml` | Build/deps | **Modificar** — adicionar dep `mcp>=1.0` + entry `kiro-dash-mcp` |
| `src/kiro_dash/mcp_server.py` | Server stdio + tool definitions | **Criar** |
| `tests/test_mcp_server.py` | Testes das tools | **Criar** |

---

### Task 1: Dependência e entry point

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Adicionar a dep e o script**

No `pyproject.toml`, em `[project] dependencies`, adicionar:

```toml
dependencies = [
    "rich>=13.7",
    "click>=8.1",
    "mcp>=1.0",
]
```

E em `[project.scripts]`:

```toml
[project.scripts]
kiro-dash = "kiro_dash.cli:main"
kiro-dash-mcp = "kiro_dash.mcp_server:main"
```

- [ ] **Step 2: Reinstalar editable**

```bash
cd /home/menzani/Desenvolvimento/mencoding/kiro-dash
source .venv/bin/activate
pip install -q -e ".[dev]"
which kiro-dash-mcp
```

Expected: imprime caminho `/home/menzani/Desenvolvimento/mencoding/kiro-dash/.venv/bin/kiro-dash-mcp`.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "build: adicionar dep mcp>=1.0 e entry point kiro-dash-mcp"
```

---

### Task 2: Funções "puras" reusáveis pelas tools

Antes de codar o server stdio, queremos uma camada que produza dicts JSON-friendly diretamente, isolada do `Console`/Rich. Isso permite testar cada tool sem subir o server.

**Files:**
- Modify: `src/kiro_dash/mcp_server.py` (criar)
- Create: `tests/test_mcp_server.py`

- [ ] **Step 1: Escrever testes**

Criar `tests/test_mcp_server.py`:

```python
"""Testes das funções de tool do servidor MCP — sem subir o stdio."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from kiro_dash.mcp_server import (
    tool_account_info,
    tool_active_sessions,
    tool_session_details,
    tool_today_summary,
    tool_top_models,
    tool_top_projects,
)
from tests.fixtures.sessions_synthetic import make_session, make_turn


def _fake_sessions():
    now = datetime.now(timezone.utc)
    return [
        make_session(
            session_id="aaaa1111-1111-1111-1111-111111111111",
            cwd="/proj/alfa",
            model_id="claude-opus-4.7",
            is_active=True,
            turns=[
                make_turn(end_timestamp=now - timedelta(minutes=5), credits=3.0),
                make_turn(end_timestamp=now - timedelta(minutes=1), credits=2.0),
            ],
        ),
        make_session(
            session_id="bbbb2222-2222-2222-2222-222222222222",
            cwd="/proj/beta",
            model_id="auto",
            is_active=False,
            updated_at=now - timedelta(hours=2),
            turns=[make_turn(end_timestamp=now - timedelta(hours=2), credits=1.5)],
        ),
    ]


def test_today_summary_aggregates_local_day():
    with patch("kiro_dash.mcp_server.load_all_sessions", return_value=_fake_sessions()):
        out = tool_today_summary()
    assert out["total_credits"] == 6.5
    assert out["total_turns"] == 3
    assert out["total_sessions"] == 2
    assert {"by_model", "by_agent", "by_cwd"} <= set(out.keys())


def test_active_sessions_returns_only_locked():
    with patch("kiro_dash.mcp_server.load_all_sessions", return_value=_fake_sessions()):
        out = tool_active_sessions()
    assert isinstance(out, list)
    assert len(out) == 1
    assert out[0]["session_id"].startswith("aaaa")
    assert out[0]["model_id"] == "claude-opus-4.7"


def test_session_details_by_prefix():
    fake = _fake_sessions()
    with patch("kiro_dash.mcp_server.find_session_by_prefix") as fp, \
         patch("kiro_dash.mcp_server.load_session_file", return_value=fake[0]):
        from pathlib import Path
        fp.return_value = Path("/tmp/aaaa.json")
        out = tool_session_details("aaaa")
    assert out is not None
    assert out["session_id"].startswith("aaaa")
    assert out["total_credits"] == 5.0
    assert out["turns_count"] == 2


def test_session_details_unknown_prefix():
    with patch("kiro_dash.mcp_server.find_session_by_prefix", return_value=None):
        out = tool_session_details("zzzz")
    assert out is None


def test_top_projects():
    with patch("kiro_dash.mcp_server.load_all_sessions", return_value=_fake_sessions()):
        out = tool_top_projects(days=7, limit=10)
    assert isinstance(out, list)
    cwds = {a["label"] for a in out}
    assert "/proj/alfa" in cwds
    assert "/proj/beta" in cwds


def test_top_models():
    with patch("kiro_dash.mcp_server.load_all_sessions", return_value=_fake_sessions()):
        out = tool_top_models(days=7, limit=10)
    labels = {a["label"] for a in out}
    assert "claude-opus-4.7" in labels


def test_account_info_when_kiro_cli_unavailable():
    with patch("kiro_dash.mcp_server.run_whoami", return_value=None):
        out = tool_account_info()
    assert out == {"available": False}


def test_account_info_returns_structured_when_available():
    from kiro_dash.account import WhoAmI
    fake = WhoAmI(
        account_type="IamIdentityCenter",
        email="x@y",
        region="sa-east-1",
        start_url=None,
        profile_name="P",
        profile_arn="arn:aws:codewhisperer:us-east-1:123456789012:profile/AB",
    )
    with patch("kiro_dash.mcp_server.run_whoami", return_value=fake):
        out = tool_account_info()
    assert out["available"] is True
    assert out["account_type"] == "IamIdentityCenter"
    assert out["aws_account_id"] == "123456789012"
    assert out["is_enterprise"] is True
```

- [ ] **Step 2: Rodar — falha**

```bash
pytest tests/test_mcp_server.py -v
```

Expected: ImportError (`kiro_dash.mcp_server`).

- [ ] **Step 3: Implementar funções de tool (sem subir server ainda)**

Criar `src/kiro_dash/mcp_server.py`:

```python
"""Servidor MCP stdio de ``kiro-dash``.

Expõe o estado de uso do Kiro CLI como ferramentas consultáveis por
outros agentes. **Cego ao conteúdo de mensagens** — só metadata
estrutural, mesmo conjunto que a CLI já expõe.

As funções ``tool_*`` produzem dicts JSON-friendly e podem ser usadas
isoladamente (testes, scripts). O server stdio em ``main()`` apenas
encaminha as chamadas MCP para elas.
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
from kiro_dash.parser import (
    find_session_by_prefix,
    load_all_sessions,
    load_session_file,
)


def _agg_to_dict(a: Aggregate) -> dict:
    return {
        "label": a.label,
        "credits": round(a.credits, 6),
        "turns": a.turns,
        "sessions": a.sessions,
        "duration_seconds": int(a.duration.total_seconds()),
        "tool_uses": a.tool_uses,
    }


def tool_today_summary() -> dict:
    """Agregado do dia local: total + breakdowns."""
    sessions = load_all_sessions()
    pairs = turns_in_local_day(sessions)
    return {
        "date": datetime.now().astimezone().date().isoformat(),
        "total_credits": round(total_credits(pairs), 6),
        "total_turns": len(pairs),
        "total_sessions": len({s.session_id for s, _ in pairs}),
        "by_model": [_agg_to_dict(a) for a in aggregate_by_model(pairs)],
        "by_agent": [_agg_to_dict(a) for a in aggregate_by_agent(pairs)],
        "by_cwd": [_agg_to_dict(a) for a in aggregate_by_cwd(pairs)],
        "by_session": [_agg_to_dict(a) for a in aggregate_by_session(pairs)],
    }


def tool_active_sessions() -> list[dict]:
    """Sessões com .lock — agentes ativos no momento."""
    sessions = load_all_sessions()
    out = []
    for s in active_sessions(sessions):
        last = s.last_turn_at or s.updated_at
        out.append({
            "session_id": s.session_id,
            "title": s.title,
            "agent_name": s.agent_name,
            "model_id": s.model_id,
            "rate_multiplier": s.rate_multiplier,
            "cwd": s.cwd,
            "turns_count": len(s.turns),
            "total_credits": round(s.total_credits, 6),
            "context_usage_pct": s.last_context_usage_pct,
            "last_turn_at": last.isoformat() if last else None,
        })
    return out


def tool_session_details(session_id_prefix: str) -> dict | None:
    """Drill-down completo (estrutural) de uma sessão por prefixo."""
    path = find_session_by_prefix(session_id_prefix)
    if path is None:
        return None
    s = load_session_file(path)
    if s is None:
        return None
    return {
        "session_id": s.session_id,
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
                "end_timestamp": t.end_timestamp.isoformat(),
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


def tool_top_projects(days: int = 7, limit: int = 10) -> list[dict]:
    """Top projetos (cwd) por créditos numa janela de N dias."""
    sessions = load_all_sessions()
    pairs = turns_in_last_days(sessions, days=days)
    return [_agg_to_dict(a) for a in aggregate_by_cwd(pairs)[:limit]]


def tool_top_models(days: int = 7, limit: int = 10) -> list[dict]:
    """Top modelos por créditos numa janela de N dias."""
    sessions = load_all_sessions()
    pairs = turns_in_last_days(sessions, days=days)
    return [_agg_to_dict(a) for a in aggregate_by_model(pairs)[:limit]]


def _whoami_to_dict(info: WhoAmI) -> dict:
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


def tool_account_info() -> dict:
    """Identidade AWS / Kiro do dispositivo atual."""
    info = run_whoami()
    if info is None:
        return {"available": False}
    return _whoami_to_dict(info)


def main() -> int:  # pragma: no cover — testado via testes E2E manuais
    """Entry point: sobe o servidor MCP stdio."""
    asyncio.run(_serve())
    return 0


async def _serve() -> None:  # pragma: no cover
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
            description="Sessões ativas (com lockfile) no momento.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="session_details",
            description="Drill-down estrutural de uma sessão por prefixo de session_id.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id_prefix": {"type": "string"},
                },
                "required": ["session_id_prefix"],
            },
        ),
        Tool(
            name="account_info",
            description="Identidade AWS / Kiro do dispositivo (saída parseada do whoami).",
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
    ]

    @app.list_tools()
    async def _list_tools() -> list[Tool]:
        return tool_specs

    @app.call_tool()
    async def _call_tool(name: str, arguments: dict) -> list[TextContent]:
        if name == "today_summary":
            payload = tool_today_summary()
        elif name == "active_sessions":
            payload = tool_active_sessions()
        elif name == "session_details":
            payload = tool_session_details(arguments.get("session_id_prefix", ""))
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
        else:
            payload = {"error": f"unknown tool: {name}"}
        return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]

    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
```

- [ ] **Step 4: Rodar testes — passa**

```bash
pytest tests/test_mcp_server.py -v
```

Expected: 8 PASSED.

- [ ] **Step 5: Smoke do entry point**

```bash
# O server lê stdio JSON-RPC. Smoke: confirma que sobe sem erro de import.
timeout 1 kiro-dash-mcp < /dev/null ; echo "rc=$?"
```

Expected: `rc=124` (timeout — server estava rodando) ou `rc=0` (saiu limpo). **NÃO pode ser `rc=1` ou `rc=2`** (erro de import / crash).

- [ ] **Step 6: Commit**

```bash
git add src/kiro_dash/mcp_server.py tests/test_mcp_server.py
git commit -m "feat(mcp): servidor stdio expondo today/active/session/account/top_*"
```

---

### Task 3: README — instruções de uso do MCP

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Adicionar seção de MCP**

Acrescentar ao final do `README.md` (antes de "Licença"):

```markdown
## MCP server — canal para outros agentes

A partir da v0.2 o `kiro-dash-mcp` expõe o estado do Kiro CLI como
ferramentas consultáveis via Model Context Protocol. Útil para agentes
fazerem meta-raciocínio sobre o próprio uso de créditos.

Registrar no Kiro CLI (assumindo que `kiro-dash-mcp` está no `PATH`):

```bash
# Adicionar ao agente (ex.: agente Nyx em ~/.kiro/agents/nyx.json)
# Em mcpServers:
"kiro-dash": {
  "command": "kiro-dash-mcp"
}
```

Tools expostas:

| Tool | Retorna |
|---|---|
| `today_summary` | Agregado do dia local |
| `active_sessions` | Sessões com lockfile no momento |
| `session_details(session_id_prefix)` | Drill-down (estrutural; sem conteúdo) |
| `account_info` | Conta, profile ARN, billing tier |
| `top_projects(days, limit)` | Top projetos por créditos |
| `top_models(days, limit)` | Top modelos por créditos |

**Privacidade:** nenhuma tool expõe conteúdo de mensagens — apenas
metadata estrutural (mesma superfície da CLI).
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: instruções de registro/uso do MCP server"
```

---

## Self-Review Checklist

- [ ] Todas as 6 funções `tool_*` retornam dicts/listas JSON-friendly (sem datetime, sem timedelta cru)
- [ ] Nenhuma tool retorna `content`/`text`/`thinking`/`input` — só metadata
- [ ] Testes cobrem: agregação, sessão ativa, drill-down, prefixo desconhecido, top_*, account info disponível e indisponível
- [ ] Entry point `kiro-dash-mcp` instalado e sobe sem erro
- [ ] Server usa `stdio_server` do pacote `mcp`
- [ ] Schema de input declarado em cada Tool
- [ ] README documenta como registrar o server num agent

## Done When

- `pytest tests/test_mcp_server.py -v` → 8 PASSED
- `which kiro-dash-mcp` resolve no venv
- `timeout 1 kiro-dash-mcp < /dev/null` retorna sem crash
- 4 commits no branch `feat/wave1-mcp-server`
