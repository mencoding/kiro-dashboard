"""Mapper schema IDE → tipo interno do kiro-dash (Wave 6 frente Q).

Converte ``IdeSession`` + ``IdeExecution[]`` em ``Session``/``Turn``
do domínio interno (``kiro_dash.models``), e ``IdeExecution`` em
``ToolCall[]`` (``kiro_dash.jsonl_parser``).

Princípios:

- Cego para conteúdo de mensagens (privacidade)
- 1 ``IdeExecution`` = 1 ``Turn``. Consolidação spec lógica
  (``intent=spec`` + ``spec-generation`` linkada) fica fora daqui
  — pode ser feita no aggregator quando necessário.
- ``selectedModel == "auto"`` → ``model_id = "kiro:auto"`` no domínio
  interno; demais valores são preservados.

Ref: plano Wave 6 frente Q, decisão #5 (mapping) e #7 (tools).
"""
from __future__ import annotations

from datetime import timedelta

from kiro_dash.backends.ide_sessions import IdeExecution, IdeSession
from kiro_dash.jsonl_parser import ToolCall
from kiro_dash.models import Session, Turn

# Constantes de identidade
SOURCE_SLUG = "ide-sessions"
AGENT_NAME = "kiro-ide"
SCHEMA_VERSION = "v1-ide"

# Contexto IDE não expõe rate_multiplier nem context_window_tokens
# explicitamente; usar defaults seguros.
DEFAULT_RATE_MULTIPLIER = 1.0
DEFAULT_CONTEXT_WINDOW_TOKENS = 200_000


def composite_session_id(session_id: str) -> str:
    """Identidade composta ``ide-sessions:<uuid>`` (ADR-0001 §"Identidade")."""
    return f"{SOURCE_SLUG}:{session_id}"


def normalize_model_id(selected_model: str) -> str:
    """``auto`` → ``kiro:auto``; demais valores preservados."""
    if selected_model == "auto":
        return "kiro:auto"
    return selected_model or "kiro:auto"


def _count_model_cycles(execution: IdeExecution) -> int:
    """Conta actions ``model`` (proxy para number_of_cycles do CLI)."""
    return sum(1 for a in execution.actions if a.action_type == "model")


def _count_tool_uses(execution: IdeExecution) -> int:
    """Conta total de tool uses (sum de len(usedTools) por fase).

    Diferente de ``len(all_used_tools)`` que de-duplica.
    """
    total = 0
    for u in execution.usage_summary:
        total += len(u.used_tools)
    return total


def to_turn(execution: IdeExecution) -> Turn:
    """Converte uma ``IdeExecution`` em ``Turn`` do domínio interno.

    Mapeamento:

    | Turn field | Origem |
    |---|---|
    | end_timestamp | ``execution.end_time`` (None se running) |
    | agent_name | ``"kiro-ide"`` |
    | parent_agent_id | None (IDE não expõe parent) |
    | duration | ``end_time - start_time`` (zero se running) |
    | end_reason | ``execution.status`` (succeed/aborted/running/failed) |
    | builtin_tool_uses | sum de len(usedTools) por fase |
    | number_of_cycles | count de actions ``model`` |
    | context_usage_pct | ``execution.context_usage_percentage`` |
    | credits | sum de ``usage_summary[].usage`` |
    """
    if execution.end_time is None:
        duration = timedelta(seconds=0)
    else:
        duration = execution.end_time - execution.start_time
    return Turn(
        end_timestamp=execution.end_time,
        agent_name=AGENT_NAME,
        parent_agent_id=None,
        duration=duration,
        end_reason=execution.status,
        builtin_tool_uses=_count_tool_uses(execution),
        number_of_cycles=_count_model_cycles(execution),
        context_usage_pct=execution.context_usage_percentage,
        credits=execution.total_credits,
    )


def to_session(
    ide_session: IdeSession,
    executions: list[IdeExecution],
) -> Session:
    """Converte ``IdeSession`` + suas executions em ``Session`` interno.

    :param ide_session: sessão IDE typed lida via ``read_session``
    :param executions: executions cuja ``chat_session_id`` aponta para
        esta sessão (fornecidas pelo caller — o mapper não faz I/O)

    O ``session_id`` é prefixado com ``ide-sessions:`` (slug do backend),
    diferenciando de sessões CLI (``cli:`` futuro). ``is_active`` é True
    se alguma execution está com status=running.
    """
    turns = [to_turn(e) for e in executions]
    is_active = any(e.is_running for e in executions)
    return Session(
        session_id=composite_session_id(ide_session.session_id),
        title=ide_session.title or None,
        agent_name=AGENT_NAME,
        model_id=normalize_model_id(ide_session.selected_model),
        rate_multiplier=DEFAULT_RATE_MULTIPLIER,
        context_window_tokens=DEFAULT_CONTEXT_WINDOW_TOKENS,
        cwd=ide_session.workspace_path,
        created_at=ide_session.date_created,
        updated_at=ide_session.mtime,
        version=SCHEMA_VERSION,
        session_created_reason=None,
        is_active=is_active,
        turns=turns,
    )


def to_tool_calls(execution: IdeExecution) -> list[ToolCall]:
    """Extrai ``ToolCall[]`` de uma execution.

    **Fonte autoritativa** (decisão #5 do plano Q): cada fase de
    ``usage_summary`` que tenha ``usedTools`` não-vazio gera 1
    ``ToolCall`` por tool.

    O ``tool_use_id`` é sintético: ``<execution_id>:<phase>:<idx>``.
    O ``session_id`` aqui é o ``chat_session_id`` da execution
    (sem prefixo composto — preservar a id raw para join com Session
    fica a cargo do aggregator).

    Status: ``"success"`` se ``execution.status == "succeed"``,
    senão ``"unknown"`` (IDE não expõe falha granular por tool).
    Erro: ``error_summary = None`` (mesma razão).
    """
    overall_status = "success" if execution.status == "succeed" else "unknown"
    out: list[ToolCall] = []
    for phase_idx, usage in enumerate(execution.usage_summary):
        for tool_idx, tool_name in enumerate(usage.used_tools):
            out.append(
                ToolCall(
                    name=tool_name,
                    tool_use_id=f"{execution.execution_id}:{phase_idx}:{tool_idx}",
                    status=overall_status,
                    session_id=execution.chat_session_id,
                    input_keys=[],
                    error_summary=None,
                )
            )
    return out


def to_tool_calls_for_session(executions: list[IdeExecution]) -> list[ToolCall]:
    """Concatena ``to_tool_calls`` para todas as executions de uma sessão."""
    out: list[ToolCall] = []
    for ex in executions:
        out.extend(to_tool_calls(ex))
    return out
