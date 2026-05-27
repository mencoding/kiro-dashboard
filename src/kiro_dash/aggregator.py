"""Agregações sobre sessões e turns parseados.

Funções puras que recebem listas de ``Session`` e produzem agregados
para os comandos da CLI (``today``, ``projects``, ``models``).
"""
from __future__ import annotations

import time as _time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from kiro_dash.models import Session, Turn


@dataclass(frozen=True, slots=True)
class Aggregate:
    """Sumário de créditos / turns / duração para um conjunto.

    Em ``aggregate_by_session`` (v0.7.0+), ``source_session_id``
    preserva o ``session_id`` raw que originou o agregado, permitindo
    que callers acessem a identidade sem parsear ``label``. Em
    agregações que cobrem múltiplas sessões (by_cwd, by_model, etc.),
    é ``None`` por design.
    """

    label: str
    credits: float
    turns: int
    sessions: int
    duration: timedelta
    tool_uses: int
    source_session_id: str | None = None


def _local_day_bounds(d: date) -> tuple[datetime, datetime]:
    """Retorna início e fim (UTC) do dia ``d`` no fuso local.

    O Kiro grava ``end_timestamp`` em UTC; nossa janela "hoje" é o dia
    civil local. Convertemos para UTC pra fazer a comparação ponto-a-ponto.
    """
    tz_local = datetime.now().astimezone().tzinfo
    start_local = datetime.combine(d, time.min, tzinfo=tz_local)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _resolve_now(now: datetime | None) -> datetime:
    """Retorna ``now`` se passado, senão ``datetime.now(timezone.utc)``."""
    return now if now is not None else datetime.now(timezone.utc)


def turns_in_local_day(
    sessions: list[Session],
    d: date | None = None,
    *,
    now: datetime | None = None,
) -> list[tuple[Session, Turn]]:
    """Retorna pares ``(sessão, turn)`` cujo turn ocorreu no dia ``d`` local.

    ``d`` default = hoje (local), derivado de ``now``.
    """
    if d is None:
        d = _resolve_now(now).astimezone().date()
    start_utc, end_utc = _local_day_bounds(d)

    out: list[tuple[Session, Turn]] = []
    for s in sessions:
        for t in s.turns_in(start_utc, end_utc):
            out.append((s, t))
    return out


def turns_in_last_days(
    sessions: list[Session],
    days: int,
    *,
    now: datetime | None = None,
) -> list[tuple[Session, Turn]]:
    """Retorna pares (sessão, turn) cujo end_timestamp caiu nos últimos N dias.

    A janela é aberta no fim (inclui o instante atual) e fechada no início
    em ``now - days``. ``days <= 0`` devolve lista vazia.
    """
    if days <= 0:
        return []
    n = _resolve_now(now)
    cutoff = n - timedelta(days=days)

    out: list[tuple[Session, Turn]] = []
    for s in sessions:
        for t in s.turns:
            if cutoff <= t.end_timestamp <= n:
                out.append((s, t))
    return out


def _aggregate_pairs(
    pairs: list[tuple[Session, Turn]],
    *,
    key,
    label_fn=str,
    carry_key_as_source: bool = False,
) -> list[Aggregate]:
    """Agrupa pares ``(sessão, turn)`` por ``key(s, t)`` e calcula totais.

    Quando ``carry_key_as_source=True``, o valor de ``key`` (tipicamente
    ``session_id`` raw) é preservado em ``Aggregate.source_session_id``.
    Útil em :func:`aggregate_by_session` para callers não precisarem
    fazer parsing reverso do ``label`` (I2 do code review Wave 6/R).
    """
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
            source_session_id=str(k) if carry_key_as_source else None,
        )
        for k, v in buckets.items()
    ]
    out.sort(key=lambda a: a.credits, reverse=True)
    return out


def filter_by_agent(
    pairs: list[tuple[Session, Turn]],
    agent: str | None,
) -> list[tuple[Session, Turn]]:
    """Filtra pares pelo ``agent_name`` da sessão. ``None`` passa tudo."""
    if agent is None:
        return pairs
    return [(s, t) for (s, t) in pairs if s.agent_name == agent]


def aggregate_by_model(pairs: list[tuple[Session, Turn]]) -> list[Aggregate]:
    """Agrega por ``model_id`` da sessão."""
    return _aggregate_pairs(pairs, key=lambda s, t: s.model_id)


def aggregate_by_agent(pairs: list[tuple[Session, Turn]]) -> list[Aggregate]:
    """Agrega por ``agent_name`` do turn (mais granular que da sessão)."""
    return _aggregate_pairs(pairs, key=lambda s, t: t.agent_name or s.agent_name or "?")


@dataclass(frozen=True, slots=True)
class AgentPairAgg:
    """Sumário cruzado runtime × persona (Wave 3 hotfix v0.4.1).

    - ``runtime`` = ``Turn.agent_name`` (engine que executou — ``kiro_default``,
      ``auto``, etc.)
    - ``persona`` = ``Session.agent_name`` (persona configurada via ``--agent``)

    Mostra simultaneamente quem executou e em nome de qual persona, evitando
    a confusão de só ver ``kiro_default`` quando todos os turns rodam sob essa
    runtime mas em sessões com personas diferentes.
    """

    runtime: str
    persona: str
    credits: float
    turns: int
    sessions: int
    duration: timedelta
    tool_uses: int


def aggregate_by_agent_pair(
    pairs: list[tuple[Session, Turn]],
) -> list[AgentPairAgg]:
    """Agrega cruzando ``Turn.agent_name`` (runtime) × ``Session.agent_name`` (persona).

    Ordenado por créditos descrescente.
    """
    buckets: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"credits": 0.0, "turns": 0, "sessions": set(),
                 "duration": timedelta(), "tools": 0}
    )
    for s, t in pairs:
        runtime = (t.agent_name or "").strip() or "?"
        persona = (s.agent_name or "").strip() or "?"
        b = buckets[(runtime, persona)]
        b["credits"] += t.credits
        b["turns"] += 1
        b["sessions"].add(s.session_id)
        b["duration"] += t.duration
        b["tools"] += t.builtin_tool_uses

    out = [
        AgentPairAgg(
            runtime=runtime,
            persona=persona,
            credits=v["credits"],
            turns=v["turns"],
            sessions=len(v["sessions"]),
            duration=v["duration"],
            tool_uses=v["tools"],
        )
        for (runtime, persona), v in buckets.items()
    ]
    out.sort(key=lambda a: a.credits, reverse=True)
    return out


def aggregate_by_cwd(pairs: list[tuple[Session, Turn]]) -> list[Aggregate]:
    """Agrega por ``cwd`` da sessão (proxy de projeto)."""
    return _aggregate_pairs(pairs, key=lambda s, t: s.cwd or "?")


def aggregate_by_project(pairs: list[tuple[Session, Turn]], *, aliases: dict[str, str] | None = None) -> list[Aggregate]:
    """Agrega por ``project_label(s.cwd, aliases=aliases)``."""
    from kiro_dash.project import project_label

    return _aggregate_pairs(pairs, key=lambda s, t: project_label(s.cwd, aliases=aliases))


def aggregate_by_session(pairs: list[tuple[Session, Turn]]) -> list[Aggregate]:
    """Agrega por ``session_id`` (label = sid curto + título).

    Em v0.7.0+ preenche ``Aggregate.source_session_id`` com o UUID raw,
    permitindo que callers (snapshots v2, MCP) acessem a identidade
    sem parsear o label.
    """
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

    return _aggregate_pairs(
        pairs,
        key=lambda s, t: s.session_id,
        label_fn=label,
        carry_key_as_source=True,
    )


def total_credits(pairs: list[tuple[Session, Turn]]) -> float:
    """Soma de créditos do conjunto."""
    return sum(t.credits for _, t in pairs)


def active_sessions(sessions: list[Session]) -> list[Session]:
    """Filtra sessões com ``is_active = True`` (lockfile presente)."""
    return [s for s in sessions if s.is_active]


def turns_in_cycle(
    sessions: list[Session],
    cycle_start: date,
    *,
    now: datetime | None = None,
) -> list[tuple[Session, Turn]]:
    """Pares (sessão, turn) com end_timestamp >= cycle_start (UTC)."""
    n = _resolve_now(now)
    tz_local = datetime.now().astimezone().tzinfo
    start_local = datetime.combine(cycle_start, time.min, tzinfo=tz_local)
    start_utc = start_local.astimezone(timezone.utc)

    out: list[tuple[Session, Turn]] = []
    for s in sessions:
        for t in s.turns:
            if start_utc <= t.end_timestamp <= n:
                out.append((s, t))
    return out


def resolve_window(
    sessions: list[Session],
    window: str,
    *,
    cycle_start: date,
    now: datetime | None = None,
) -> list[tuple[Session, Turn]]:
    """Resolve uma janela nomeada para pares (sessão, turn).

    Aceita: today, week, month, cycle, all, ou string inteiro (dias).
    """
    w = window.strip().lower()
    if w == "today":
        return turns_in_local_day(sessions, now=now)
    if w == "week":
        return turns_in_last_days(sessions, days=7, now=now)
    if w == "month":
        return turns_in_last_days(sessions, days=30, now=now)
    if w == "cycle":
        return turns_in_cycle(sessions, cycle_start, now=now)
    if w == "all":
        return [(s, t) for s in sessions for t in s.turns]
    try:
        n = int(w)
    except ValueError as exc:
        raise ValueError(
            f"window inválido: '{window}'. Use today/week/month/cycle/all ou um inteiro de dias."
        ) from exc
    if n < 0:
        raise ValueError(f"window negativo: {n}")
    return turns_in_last_days(sessions, days=n, now=now)


def balance_in_cycle(
    sessions: list[Session],
    cycle_start: date,
    *,
    monthly_credits: int,
    now: datetime | None = None,
) -> dict:
    """Calcula saldo do ciclo: consumed / remaining / pct_used."""
    pairs = turns_in_cycle(sessions, cycle_start, now=now)
    consumed = sum(t.credits for _, t in pairs)
    remaining = monthly_credits - consumed
    pct = (consumed / monthly_credits * 100.0) if monthly_credits > 0 else 0.0
    return {
        "consumed": round(consumed, 6),
        "remaining": round(remaining, 6),
        "pct_used": round(pct, 2),
        "monthly_credits": monthly_credits,
        "cycle_start": cycle_start,
        "turns": len(pairs),
        "sessions": len({s.session_id for s, _ in pairs}),
    }


from kiro_dash.jsonl_parser import iter_tool_calls


def aggregate_tools_in_window(
    sessions_dir: Path,
    *,
    hours: int = 24,
) -> list[dict]:
    """Conta tool calls em ``.jsonl`` cujo mtime cai na janela."""
    if not sessions_dir.is_dir():
        return []

    cutoff = _time.time() - hours * 3600
    counts: Counter[str] = Counter()
    sessions_by_name: dict[str, set[str]] = defaultdict(set)
    errors_by_name: Counter[str] = Counter()

    for path in sessions_dir.iterdir():
        if not (path.is_file() and path.suffix == ".jsonl"):
            continue
        try:
            if path.stat().st_mtime < cutoff:
                continue
        except OSError:
            continue
        for call in iter_tool_calls(path):
            counts[call.name] += 1
            sessions_by_name[call.name].add(call.session_id)
            if call.status == "error":
                errors_by_name[call.name] += 1

    return [
        {
            "name": name,
            "count": cnt,
            "sessions": len(sessions_by_name[name]),
            "errors": errors_by_name[name],
        }
        for name, cnt in counts.most_common()
    ]
