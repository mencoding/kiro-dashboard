"""Camada de fronteira — backends que leem fontes externas do Kiro.

Princípio do ADR-0001: cada backend encapsula leitura de uma fonte
(filesystem do CLI, sqlite do CLI, state.vscdb do IDE, sessions IDE) e
expõe uma interface comum. O domínio do `kiro-dash` (aggregator,
snapshots, history, views, MCP) consome via `sources.Sources`, sem
acoplamento ao schema externo.

Princípio operacional reforçado: **read-only forte**. Backends abrem
arquivos em `O_RDONLY` e sqlites em `?mode=ro`. Nunca escrevem na fonte
externa, nunca acionam migrations.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum, auto


class Capability(Enum):
    """Conceitos que um backend pode fornecer.

    Backends declaram quais capabilities oferecem via
    :meth:`Backend.capabilities`. O detector ``Sources`` enumera fontes
    disponíveis por capability para o aggregator escolher a melhor.
    """

    USAGE_STATE = auto()
    """Saldo/uso de créditos autoritativo (servidor Kiro)."""

    SESSIONS = auto()
    """Listagem de sessões (catálogo)."""

    TURNS = auto()
    """Turns/turnos com créditos por turn."""

    TOOL_CALLS = auto()
    """Tool calls disparadas em cada turn."""

    RUNNING = auto()
    """Detecção de sessão em curso (live)."""

    ACCOUNT = auto()
    """Identidade da conta (ARN, profile name)."""


class Backend(ABC):
    """Interface comum para fontes de dados Kiro.

    Subclasses concretas:
    - ``CliJsonBackend``: ``~/.kiro/sessions/cli/*.{json,jsonl,lock}``
    - ``IdeStateBackend``: ``~/.config/Kiro/.../state.vscdb`` (kiro.kiroAgent)
    - ``IdeSessionBackend``: ``~/.config/Kiro/.../kiro.kiroagent/...``
    - ``CliSqliteBackend`` (futuro): ``~/.local/share/kiro-cli/data.sqlite3``

    Convenções:
    - ``slug`` é detalhe de identidade interna (ver ADR-0001 §
      "Identidade de sessão composta"); compõe ``internal_session_id``
      como ``"<slug>:<source_session_id>"``.
    - ``is_available()`` é check leve, idempotente, sem efeitos
      colaterais. Pode ser chamado várias vezes na mesma execução.
    - ``data_age()`` retorna idade em segundos do dado mais recente, ou
      ``None`` se a noção de idade não se aplica (filesystem live como
      ``CliJsonBackend`` retorna ``None``).
    """

    @property
    @abstractmethod
    def slug(self) -> str:
        """Identificador único e estável do backend."""

    @abstractmethod
    def is_available(self) -> bool:
        """Verifica se a fonte está disponível e em formato reconhecido."""

    @abstractmethod
    def capabilities(self) -> set[Capability]:
        """Conjunto de capabilities que esta fonte fornece."""

    def data_age(self) -> float | None:
        """Idade (s) do dado mais recente; ``None`` se irrelevante.

        Default: ``None`` (apropriado para fontes live de filesystem).
        Backends com cache externo (ex.: ``IdeStateBackend`` que lê
        snapshot do servidor) devem sobrescrever.
        """
        return None
