"""Modelos de dados — sessões e turns do Kiro CLI.

Princípio de privacidade: estes modelos são deliberadamente cegos para
conteúdo de mensagens. Carregam APENAS metadata estrutural (créditos,
modelo, timestamps, contagens). O conteúdo de
``result.Ok.content[].data`` no JSON original nunca é referenciado.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable


@dataclass(frozen=True, slots=True)
class Turn:
    """Um user-turn de uma sessão do Kiro CLI.

    Corresponde a uma entry de
    ``session_state.conversation_metadata.user_turn_metadatas[]``.

    Atributos
    ---------
    end_timestamp:
        ISO 8601 UTC do fim do turno (campo ``end_timestamp``).
    agent_name:
        Nome do agent (``loop_id.agent_id.name``) — ex.: ``kiro_default``,
        ``nyx``.
    parent_agent_id:
        Identificador opaco do agent pai quando este turno foi rodado por
        um subagent. ``None`` para turnos top-level.
    duration:
        Duração do turno (``turn_duration.secs`` + ``.nanos`` consolidados).
    end_reason:
        Razão de término reportada pelo Kiro (ex.: ``UserTurnEnd``).
    builtin_tool_uses:
        Contagem de tool calls builtin disparadas durante o turno.
    number_of_cycles:
        Número de ciclos internos do agent (think→act→observe).
    context_usage_pct:
        % do context window consumido ao fim do turno (0–100).
    credits:
        Créditos faturados no turno (soma de ``metering_usage[].value``).
    """

    end_timestamp: datetime
    agent_name: str
    parent_agent_id: str | None
    duration: timedelta
    end_reason: str
    builtin_tool_uses: int
    number_of_cycles: int
    context_usage_pct: float
    credits: float


@dataclass(frozen=True, slots=True)
class Session:
    """Uma sessão completa do Kiro CLI.

    Atributos
    ---------
    session_id:
        UUID da sessão (nome do arquivo ``.json``).
    title:
        Título da sessão (geralmente derivado da primeira mensagem do
        usuário). ``None`` se ausente.
    agent_name:
        Agent ativo da sessão (``session_state.agent_name``).
    model_id:
        Identificador do modelo (``model_info.model_id``); pode ser
        ``"auto"`` ou nome específico (``claude-opus-4.7``, etc.).
    rate_multiplier:
        Multiplicador de cobrança do modelo (Opus 4.7 = 2.2).
    context_window_tokens:
        Capacidade do context window do modelo, em tokens.
    cwd:
        Diretório de trabalho onde a sessão foi iniciada.
    created_at / updated_at:
        Timestamps ISO 8601 UTC do JSON.
    version:
        Versão do schema da sessão (atualmente ``v1``).
    session_created_reason:
        Razão de criação reportada pelo Kiro (ex.: ``subagent``).
        ``None`` em sessões antigas que não tinham o campo.
    is_active:
        ``True`` se há ``.lock`` ao lado do ``.json``.
    turns:
        Lista de ``Turn`` em ordem de ocorrência.
    """

    session_id: str
    title: str | None
    agent_name: str
    model_id: str
    rate_multiplier: float
    context_window_tokens: int
    cwd: str
    created_at: datetime
    updated_at: datetime
    version: str
    session_created_reason: str | None
    is_active: bool
    turns: list[Turn] = field(default_factory=list)

    @property
    def total_credits(self) -> float:
        """Soma de créditos de todos os turns."""
        return sum(t.credits for t in self.turns)

    @property
    def total_duration(self) -> timedelta:
        """Soma da duração de todos os turns."""
        return sum((t.duration for t in self.turns), timedelta())

    @property
    def total_tool_uses(self) -> int:
        """Soma de builtin_tool_uses de todos os turns."""
        return sum(t.builtin_tool_uses for t in self.turns)

    @property
    def last_context_usage_pct(self) -> float:
        """% de contexto no último turno (0 se sessão sem turns)."""
        return self.turns[-1].context_usage_pct if self.turns else 0.0

    @property
    def last_turn_at(self) -> datetime | None:
        """Timestamp do último turno (None se sem turns)."""
        return self.turns[-1].end_timestamp if self.turns else None

    def turns_in(self, start: datetime, end: datetime) -> Iterable[Turn]:
        """Itera turns cujo ``end_timestamp`` cai em ``[start, end)``."""
        return (t for t in self.turns if start <= t.end_timestamp < end)
