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

# IDE não expõe context_window_tokens; default seguro.
# Em payloads MCP, este placeholder é serializado como ``null`` para
# sessões IDE (decisão I6 do code review Wave 6/R).
DEFAULT_CONTEXT_WINDOW_TOKENS = 200_000

# T1-W7: tabela de rate_multiplier por modelo Kiro conhecido.
# Valores correspondem ao multiplicador de cobrança Kiro CLI/IDE,
# observado no campo ``model_info.rate_multiplier`` das sessões CLI.
# Quando o IDE reporta ``selectedModel`` na sessão, mapeamos via
# busca em prefixos (mais robusto a variantes de versão).
#
# Referência: Anthropic pricing 2026 + observação local em parser.py.
_MODEL_RATE_MULTIPLIERS: dict[str, float] = {
    # Claude Opus
    "claude-opus-4.7": 2.2,
    "claude-opus-4.5": 2.2,
    "claude-opus-4": 2.0,
    "claude-opus": 2.0,
    # Claude Sonnet
    "claude-sonnet-4.5": 1.0,
    "claude-sonnet-4": 1.0,
    "claude-sonnet": 1.0,
    "claude-3.5-sonnet": 1.0,
    # Claude Haiku
    "claude-haiku-4.5": 0.3,
    "claude-haiku-4": 0.3,
    "claude-haiku": 0.3,
    # Auto/desconhecido
    "auto": 1.0,
    "kiro:auto": 1.0,
}
"""Mapping de modelo conhecido para rate_multiplier (T1-W7)."""

DEFAULT_RATE_MULTIPLIER = 1.0
"""Fallback quando ``selected_model`` não casa com nenhum prefixo conhecido."""


def rate_multiplier_for_model(model_id: str) -> float:
    """Resolve ``rate_multiplier`` a partir do ``model_id``.

    Match em duas etapas:
    1. Lookup exato em ``_MODEL_RATE_MULTIPLIERS``
    2. Match por prefixo (``startswith``) — mais permissivo para
       variantes de versão (ex.: ``claude-opus-4.7-20251015``)

    Retorna :data:`DEFAULT_RATE_MULTIPLIER` (1.0) se nada bater.
    """
    if not model_id:
        return DEFAULT_RATE_MULTIPLIER
    # Match exato
    direct = _MODEL_RATE_MULTIPLIERS.get(model_id)
    if direct is not None:
        return direct
    # Match por prefixo (ordenar por comprimento desc para preferir match mais específico)
    keys_by_specificity = sorted(_MODEL_RATE_MULTIPLIERS.keys(), key=len, reverse=True)
    for key in keys_by_specificity:
        if model_id.startswith(key):
            return _MODEL_RATE_MULTIPLIERS[key]
    return DEFAULT_RATE_MULTIPLIER


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
    model_id = normalize_model_id(ide_session.selected_model)
    return Session(
        session_id=composite_session_id(ide_session.session_id),
        title=ide_session.title or None,
        agent_name=AGENT_NAME,
        model_id=model_id,
        rate_multiplier=rate_multiplier_for_model(model_id),
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


# ── T2-W7: Consolidação spec lógica ─────────────────────────────────


def _is_spec_dispatch(ex: "IdeExecution") -> bool:
    """``True`` para chat-agent com intent.classification == 'spec'."""
    return (
        ex.workflow_type == "chat-agent"
        and ex.intent_result is not None
        and ex.intent_result.classification == "spec"
    )


def _is_spec_generation(ex: "IdeExecution") -> bool:
    """``True`` para workflow_type == 'spec-generation'."""
    return ex.workflow_type == "spec-generation"


def consolidate_spec_executions(
    executions: list["IdeExecution"],
) -> list["IdeExecution"]:
    """Funde pares chat-agent intent=spec + spec-generation em 1 turn lógico.

    Quando o IDE recebe um pedido de spec, dispara duas executions
    encadeadas no mesmo ``chat_session_id``: a primeira (``chat-agent``
    intent=spec) é só dispatcher leve; a segunda (``spec-generation``)
    é a sub-execução pesada que gera os arquivos.

    Esta função detecta esse padrão (executions ordenadas por start_time)
    e produz um único ``IdeExecution`` "lógico" combinando:

    - ``execution_id``: do dispatcher (preserva identidade do turn)
    - ``actions``: concatenação (dispatcher + generation)
    - ``usage_summary``: concatenação
    - ``status``: do generation (final)
    - ``end_time``: do generation (final)
    - ``start_time``: do dispatcher (início)
    - ``intent_result``: do dispatcher (que tinha o classifier)
    - ``workflow_type``: ``chat-agent`` (preservar tipo do turn raiz)

    Retorna **nova** lista; não muta executions originais. Executions
    sem padrão spec passam inalteradas.

    Esta função é **opt-in**: callers que querem visão "raw" (1
    execution = 1 turn) não chamam. Callers que querem visão "lógica"
    (1 spec request = 1 turn agregado) aplicam antes de :func:`to_session`.
    """
    if not executions:
        return []

    # Ordenar por start_time para detecção sequencial
    sorted_exs = sorted(executions, key=lambda e: e.start_time)
    out: list[IdeExecution] = []
    skip_indices: set[int] = set()

    for i, ex in enumerate(sorted_exs):
        if i in skip_indices:
            continue
        # Detectar dispatcher seguido de generation
        if _is_spec_dispatch(ex):
            for j in range(i + 1, len(sorted_exs)):
                if j in skip_indices:
                    continue
                next_ex = sorted_exs[j]
                if _is_spec_generation(next_ex) and next_ex.start_time >= ex.start_time:
                    # Funde em IdeExecution lógico
                    merged = IdeExecution(
                        execution_id=ex.execution_id,
                        chat_session_id=ex.chat_session_id,
                        workflow_type="chat-agent",  # raiz preservada
                        status=next_ex.status,
                        start_time=ex.start_time,
                        end_time=next_ex.end_time,
                        autonomy_mode=ex.autonomy_mode,
                        actions=ex.actions + next_ex.actions,
                        usage_summary=ex.usage_summary + next_ex.usage_summary,
                        intent_result=ex.intent_result,
                        context_usage_percentage=max(
                            ex.context_usage_percentage,
                            next_ex.context_usage_percentage,
                        ),
                        mtime=max(ex.mtime, next_ex.mtime),
                    )
                    out.append(merged)
                    skip_indices.add(j)
                    break
            else:
                # Dispatcher sem generation linkada — manter raw
                out.append(ex)
        else:
            out.append(ex)

    return out
