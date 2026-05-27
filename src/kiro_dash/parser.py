"""Parser de arquivos de sessão do Kiro CLI.

Lê arquivos ``~/.kiro/sessions/cli/<sid>.json`` e produz instâncias de
``Session`` / ``Turn`` (ver ``models.py``).

**Princípio de privacidade**: este módulo é cego para conteúdo de
mensagens. Nunca acessa ``result.Ok.content[].data`` nem campos
correlatos. Apenas metadata estrutural é extraída.

Tolerância a schema:
- Campos opcionais ausentes -> defaults seguros (``None``, ``0``, ``""``)
- ``model_info`` parcial -> ``model_id="?"``, ``rate_multiplier=0.0``
- Turn malformado é silenciosamente ignorado (não derruba a sessão)
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from kiro_dash.models import LockInfo, Session, Turn

DEFAULT_SESSIONS_DIR = Path.home() / ".kiro" / "sessions" / "cli"


def _parse_iso(value: str | None) -> datetime | None:
    """Parseia ISO 8601 com sufixo ``Z`` ou offset; retorna None em falha."""
    if not value:
        return None
    try:
        # Normaliza sufixo Z para +00:00 (datetime.fromisoformat aceita ambos
        # em Python 3.11+, mas defensivo).
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _parse_duration(d: dict | None) -> timedelta:
    """Converte ``{secs, nanos}`` em ``timedelta`` (defensivo)."""
    if not isinstance(d, dict):
        return timedelta()
    secs = d.get("secs", 0) or 0
    nanos = d.get("nanos", 0) or 0
    return timedelta(seconds=secs, microseconds=nanos // 1000)


def _sum_metering_credits(metering_usage: list | None) -> float:
    """Soma ``value`` de entries com ``unit == 'credit'`` (case-insensitive)."""
    if not isinstance(metering_usage, list):
        return 0.0
    total = 0.0
    for entry in metering_usage:
        if not isinstance(entry, dict):
            continue
        unit = str(entry.get("unit", "")).lower()
        if unit != "credit":
            continue
        try:
            total += float(entry.get("value", 0) or 0)
        except (TypeError, ValueError):
            continue
    return total


def parse_turn(raw: dict) -> Turn | None:
    """Parseia um item de ``user_turn_metadatas[]``.

    Retorna ``None`` se o turno não tiver ``end_timestamp`` válido — é o
    único campo realmente obrigatório para o painel; sem ele não há como
    atribuir o consumo no tempo.

    Não lê ``result.Ok.content`` (privacidade).
    """
    if not isinstance(raw, dict):
        return None

    end_ts = _parse_iso(raw.get("end_timestamp"))
    if end_ts is None:
        return None

    loop_id = raw.get("loop_id") or {}
    agent_id = loop_id.get("agent_id") or {}
    agent_name = str(agent_id.get("name", "") or "")
    parent_id_raw = agent_id.get("parent_id")
    parent_agent_id = str(parent_id_raw) if parent_id_raw else None

    return Turn(
        end_timestamp=end_ts,
        agent_name=agent_name,
        parent_agent_id=parent_agent_id,
        duration=_parse_duration(raw.get("turn_duration")),
        end_reason=str(raw.get("end_reason", "") or ""),
        builtin_tool_uses=int(raw.get("builtin_tool_uses", 0) or 0),
        number_of_cycles=int(raw.get("number_of_cycles", 0) or 0),
        context_usage_pct=float(raw.get("context_usage_percentage", 0.0) or 0.0),
        credits=_sum_metering_credits(raw.get("metering_usage")),
    )


def parse_session(raw: dict, *, is_active: bool = False) -> Session | None:
    """Parseia o JSON top-level de uma sessão.

    Retorna ``None`` se faltar ``session_id`` (sem identidade não há nada
    a fazer).
    """
    if not isinstance(raw, dict):
        return None

    session_id = raw.get("session_id")
    if not session_id:
        return None

    state = raw.get("session_state") or {}
    rts = state.get("rts_model_state") or {}
    model_info = rts.get("model_info") or {}

    created_at = _parse_iso(raw.get("created_at"))
    updated_at = _parse_iso(raw.get("updated_at"))

    if created_at is None or updated_at is None:
        # Sessão sem timestamps básicos é inutilizável para o painel.
        return None

    conv_meta = state.get("conversation_metadata") or {}
    raw_turns = conv_meta.get("user_turn_metadatas") or []

    turns: list[Turn] = []
    for r in raw_turns:
        t = parse_turn(r)
        if t is not None:
            turns.append(t)

    # Ordem cronológica defensiva (esperamos append-only, mas barato garantir).
    turns.sort(key=lambda t: t.end_timestamp)

    return Session(
        session_id=str(session_id),
        title=raw.get("title") or None,
        agent_name=str(state.get("agent_name", "") or ""),
        model_id=str(model_info.get("model_id", "?") or "?"),
        rate_multiplier=float(model_info.get("rate_multiplier", 0.0) or 0.0),
        context_window_tokens=int(model_info.get("context_window_tokens", 0) or 0),
        cwd=str(raw.get("cwd", "") or ""),
        created_at=created_at,
        updated_at=updated_at,
        version=str(state.get("version", "") or ""),
        session_created_reason=raw.get("session_created_reason") or None,
        is_active=is_active,
        turns=turns,
    )


def load_session_file(path: Path) -> Session | None:
    """Carrega e parseia um ``<sid>.json`` do disco.

    ``is_active`` é determinado pela presença de ``<sid>.lock`` no mesmo
    diretório.
    """
    try:
        with path.open(encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None

    lock_path = path.with_suffix(".lock")
    is_active = lock_path.exists()

    return parse_session(raw, is_active=is_active)


def discover_sessions(sessions_dir: Path | None = None) -> list[Path]:
    """Lista paths de ``<sid>.json`` em ``~/.kiro/sessions/cli/``.

    Não inclui ``.jsonl``, ``.lock`` nem subdiretórios. Ordem por mtime
    decrescente (sessões recentes primeiro) para facilitar inspeção
    "live".
    """
    base = sessions_dir or DEFAULT_SESSIONS_DIR
    if not base.is_dir():
        return []

    paths = [p for p in base.iterdir() if p.is_file() and p.suffix == ".json"]
    paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return paths


def find_session_by_prefix(
    prefix: str,
    sessions_dir: Path | None = None,
) -> Path | None:
    """Procura uma sessão cujo ``session_id`` comece com ``prefix``.

    Retorna o ``Path`` único quando o prefixo é não-ambíguo; ``None`` se
    nenhum ou múltiplos casam.
    """
    base = sessions_dir or DEFAULT_SESSIONS_DIR
    if not base.is_dir():
        return None

    matches = [
        p for p in base.iterdir()
        if p.is_file() and p.suffix == ".json" and p.stem.startswith(prefix)
    ]
    if len(matches) != 1:
        return None
    return matches[0]


def load_all_sessions(sessions_dir: Path | None = None) -> list[Session]:
    """Carrega todas as sessões parseáveis em ``sessions_dir``.

    Sessões com erro de parse são silenciosamente puladas — comportamento
    deliberado para tolerância a logs corrompidos / schema antigo.
    """
    out: list[Session] = []
    for path in discover_sessions(sessions_dir):
        s = load_session_file(path)
        if s is not None:
            out.append(s)
    return out


def read_lock(sid: str, sessions_dir: Path | None = None) -> LockInfo | None:
    """Lê ``<sid>.lock`` e devolve ``LockInfo`` ou ``None``."""
    base = sessions_dir or DEFAULT_SESSIONS_DIR
    lock_path = base / f"{sid}.lock"
    if not lock_path.exists():
        return None
    try:
        with open(lock_path) as f:
            data = json.load(f)
        started_at = _parse_iso(data["started_at"])
        if started_at is None:
            return None
        return LockInfo(pid=int(data["pid"]), started_at=started_at)
    except (OSError, KeyError, ValueError, json.JSONDecodeError):
        return None
