"""Agregações sobre sessões e turns parseados.

Funções puras que recebem listas de ``Session`` e produzem agregados
para os comandos da CLI (``today``, ``projects``, ``models``).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from kiro_dash.models import Session, Turn


@dataclass(frozen=True, slots=True)
class Aggregate:
    """Sumário de créditos / turns / duração para um conjunto."""

    label: str
    credits: float
    turns: int
    sessions: int
    duration: timedelta
    tool_uses: int


def _local_day_bounds(d: date) -> tuple[datetime, datetime]:
    """Retorna início e fim (UTC) do dia ``d`` no fuso local.

    O Kiro grava ``end_timestamp`` em UTC; nossa janela "hoje" é o dia
    civil local. Convertemos para UTC pra fazer a comparação ponto-a-ponto.
    """
    tz_local = datetime.now().astimezone().tzinfo
    start_local = datetime.combine(d, time.min, tzinfo=tz_local)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def turns_in_local_day(
    sessions: list[Session],
    d: date | None = None,
) -> list[tuple[Session, Turn]]:
    """Retorna pares ``(sessão, turn)`` cujo turn ocorreu no dia ``d`` local.

    ``d`` default = hoje (local).
    """
    if d is None:
        d = datetime.now().astimezone().date()
    start_utc, end_utc = _local_day_bounds(d)

    out: list[tuple[Session, Turn]] = []
    for s in sessions:
        for t in s.turns_in(start_utc, end_utc):
            out.append((s, t))
    return out


def turns_in_last_days(
    sessions: list[Session],
    days: int,
) -> list[tuple[Session, Turn]]:
    """Retorna pares (sessão, turn) cujo end_timestamp caiu nos últimos N dias.

    A janela é aberta no fim (inclui o instante atual) e fechada no início
    em ``now - days``. ``days <= 0`` devolve lista vazia.
    """
    if days <= 0:
        return []
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    out: list[tuple[Session, Turn]] = []
    for s in sessions:
        for t in s.turns:
            if cutoff <= t.end_timestamp <= now:
                out.append((s, t))
    return out


def _aggregate_pairs(
    pairs: list[tuple[Session, Turn]],
    *,
    key,
    label_fn=str,
) -> list[Aggregate]:
    """Agrupa pares ``(sessão, turn)`` por ``key(s, t)`` e calcula totais."""
    buckets: dict[object, dict] = defaultdict(
        lambda: {"credits": 0.0, "turns": 0, "sessions": set(), "duration": timedelta(), "tools": 0}
    )
    for s, t in pairs:
        k = key(s, t)
        b = buckets[k]
        b["credits"] += t.credits
        b["turns"] += 1
        b["sessions"].add(s.session_id)
        b["duration"] += t.duration
        b["tools"] += t.builtin_tool_uses

    out = [
        Aggregate(
            label=label_fn(k),
            credits=v["credits"],
            turns=v["turns"],
            sessions=len(v["sessions"]),
            duration=v["duration"],
            tool_uses=v["tools"],
        )
        for k, v in buckets.items()
    ]
    out.sort(key=lambda a: a.credits, reverse=True)
    return out


def aggregate_by_model(pairs: list[tuple[Session, Turn]]) -> list[Aggregate]:
    """Agrega por ``model_id`` da sessão."""
    return _aggregate_pairs(pairs, key=lambda s, t: s.model_id)


def aggregate_by_agent(pairs: list[tuple[Session, Turn]]) -> list[Aggregate]:
    """Agrega por ``agent_name`` do turn (mais granular que da sessão)."""
    return _aggregate_pairs(pairs, key=lambda s, t: t.agent_name or s.agent_name or "?")


def aggregate_by_cwd(pairs: list[tuple[Session, Turn]]) -> list[Aggregate]:
    """Agrega por ``cwd`` da sessão (proxy de projeto)."""
    return _aggregate_pairs(pairs, key=lambda s, t: s.cwd or "?")


def aggregate_by_session(pairs: list[tuple[Session, Turn]]) -> list[Aggregate]:
    """Agrega por ``session_id`` (label = sid curto + título)."""
    def label(sid: str) -> str:
        # Recupera título do session em pairs
        for s, _ in pairs:
            if s.session_id == sid:
                short = sid[:8]
                title = (s.title or "").strip()
                if title:
                    return f"{short} {title[:60]}"
                return short
        return sid[:8]

    return _aggregate_pairs(pairs, key=lambda s, t: s.session_id, label_fn=label)


def total_credits(pairs: list[tuple[Session, Turn]]) -> float:
    """Soma de créditos do conjunto."""
    return sum(t.credits for _, t in pairs)


def active_sessions(sessions: list[Session]) -> list[Session]:
    """Filtra sessões com ``is_active = True`` (lockfile presente)."""
    return [s for s in sessions if s.is_active]
