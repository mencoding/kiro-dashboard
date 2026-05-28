"""``IdeStateBackend`` — billing autoritativo do servidor Kiro via IDE.

Lê a chave ``kiro.kiroAgent`` do ``state.vscdb`` (sqlite VS Code-style)
do Kiro IDE em ``~/.config/Kiro/User/globalStorage/state.vscdb``.

O IDE faz fetch periódico (~30-60s enquanto rodando) do billing global
da conta Kiro e cacheia ali. O backend lê esse cache em modo somente
leitura, sem competir com o IDE pela escrita.

Princípio operacional do ADR-0001: read-only forte, retry em
``SQLITE_BUSY``, schema check defensivo.
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from kiro_dash.backends import Backend, Capability

from kiro_dash._platform_paths import kiro_ide_state_db_path

DEFAULT_IDE_STATE_VSCDB = kiro_ide_state_db_path()
"""Caminho default do ``state.vscdb`` global do Kiro IDE.

Cross-platform via :mod:`kiro_dash._platform_paths`:
- Linux: ``~/.config/Kiro/User/globalStorage/state.vscdb``
- Windows: ``%APPDATA%/Kiro/User/globalStorage/state.vscdb``
- macOS: ``~/Library/Application Support/Kiro/User/globalStorage/state.vscdb``
"""

KIRO_AGENT_KEY = "kiro.kiroAgent"
"""Chave dentro de ``ItemTable`` que carrega o JSON de uso/billing."""

USAGE_STATE_FIELD = "kiro.resourceNotifications.usageState"
"""Campo dentro do JSON com o breakdown de uso autoritativo."""

# Tentativas de retry em caso de SQLITE_BUSY (IDE escrevendo concorrente)
_RETRY_ATTEMPTS = 3
_RETRY_DELAY_S = 0.05


class IdeStateError(Exception):
    """Erro genérico de leitura do state.vscdb do IDE."""


class IdeStateSchemaError(IdeStateError):
    """Schema do `kiro.kiroAgent` em formato não reconhecido.

    Carrega ``observed_keys`` (top-level keys do JSON observado) para
    facilitar debug de mudanças de schema entre versões do Kiro IDE.
    """

    def __init__(self, message: str, *, observed_keys: list[str] | None = None):
        super().__init__(message)
        self.observed_keys = observed_keys or []


@dataclass(frozen=True, slots=True)
class IdeUsageState:
    """Snapshot de uso autoritativo do servidor Kiro.

    Mapeia 1:1 com o primeiro entry de
    ``kiro.resourceNotifications.usageState.usageBreakdowns[]`` no JSON
    do IDE, mais o ``timestamp`` da estrutura pai.

    Atributos
    ---------
    current_usage:
        Créditos consumidos no período corrente.
    usage_limit:
        Limite do plano (créditos).
    percentage_used:
        ``current_usage / usage_limit * 100``, conforme servidor.
    current_overages:
        Créditos consumidos acima do limite no período.
    overage_cap:
        Limite máximo de overage permitido.
    overage_charges:
        Cobranças (em moeda) já incorridas por overage.
    overage_rate:
        Taxa por unidade acima do limite (em moeda da conta).
    reset_date:
        Data UTC em que o ``current_usage`` reseta.
    currency_code:
        ISO 4217 (ex.: ``"USD"``).
    currency_symbol:
        Símbolo (ex.: ``"$"``).
    unit:
        Unidade do consumo (ex.: ``"INVOCATIONS"``).
    type:
        Tipo do recurso (ex.: ``"CREDIT"``).
    timestamp:
        UTC do momento em que o IDE refrescou o cache do servidor.
    schema_version_observed:
        Versão convencionada pelo kiro-dash; ``1`` para o shape atual
        observado em 2026-05-27.
    """

    current_usage: float
    usage_limit: float
    percentage_used: float
    current_overages: float
    overage_cap: float
    overage_charges: float
    overage_rate: float
    reset_date: datetime
    currency_code: str
    currency_symbol: str
    unit: str
    type: str
    timestamp: datetime
    schema_version_observed: int = 1

    @property
    def age_seconds(self) -> float:
        """Idade do snapshot em segundos (UTC now - timestamp)."""
        return (datetime.now(timezone.utc) - self.timestamp).total_seconds()


def _parse_iso_utc(value: str) -> datetime:
    """Parseia ISO 8601 com sufixo Z; sempre retorna UTC."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _ms_to_dt_utc(ms: int | float) -> datetime:
    """Converte epoch milliseconds para datetime UTC."""
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


def _open_ro(path: Path) -> sqlite3.Connection:
    """Abre conexão read-only com retry em SQLITE_BUSY."""
    last_err: sqlite3.OperationalError | None = None
    for attempt in range(_RETRY_ATTEMPTS):
        try:
            return sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        except sqlite3.OperationalError as e:
            last_err = e
            if attempt < _RETRY_ATTEMPTS - 1:
                time.sleep(_RETRY_DELAY_S)
    assert last_err is not None
    raise last_err


def _read_kiro_agent_blob(path: Path) -> dict | None:
    """Lê e desserializa o BLOB de ``kiro.kiroAgent``; ``None`` se ausente."""
    if not path.is_file():
        return None
    con = _open_ro(path)
    try:
        cur = con.cursor()
        try:
            cur.execute("SELECT value FROM ItemTable WHERE key = ?", (KIRO_AGENT_KEY,))
        except sqlite3.OperationalError:
            return None
        row = cur.fetchone()
        if row is None:
            return None
        raw = row[0]
        if isinstance(raw, bytes):
            text = raw.decode("utf-8")
        else:
            text = str(raw)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None
    finally:
        con.close()


def _parse_usage_state(payload: dict) -> IdeUsageState:
    """Extrai ``IdeUsageState`` do JSON do ``kiro.kiroAgent``.

    Levanta :exc:`IdeStateSchemaError` se campos obrigatórios estiverem
    ausentes ou no shape errado.
    """
    if not isinstance(payload, dict):
        raise IdeStateSchemaError(
            "kiro.kiroAgent não é um objeto JSON",
            observed_keys=[],
        )
    usage_state = payload.get(USAGE_STATE_FIELD)
    if not isinstance(usage_state, dict):
        raise IdeStateSchemaError(
            f"campo {USAGE_STATE_FIELD!r} ausente ou inválido",
            observed_keys=sorted(payload.keys()),
        )
    breakdowns = usage_state.get("usageBreakdowns")
    if not isinstance(breakdowns, list) or not breakdowns:
        raise IdeStateSchemaError(
            "usageBreakdowns vazio ou inválido",
            observed_keys=sorted(usage_state.keys()),
        )
    b = breakdowns[0]
    if not isinstance(b, dict):
        raise IdeStateSchemaError("usageBreakdowns[0] não é objeto")

    required = (
        "currentUsage",
        "usageLimit",
        "percentageUsed",
        "resetDate",
        "currency",
        "unit",
    )
    missing = [k for k in required if k not in b]
    if missing:
        raise IdeStateSchemaError(
            f"campos obrigatórios faltando em usageBreakdowns[0]: {missing}",
            observed_keys=sorted(b.keys()),
        )

    currency = b.get("currency") or {}
    if not isinstance(currency, dict):
        raise IdeStateSchemaError("currency não é objeto")

    timestamp_ms = usage_state.get("timestamp")
    if not isinstance(timestamp_ms, (int, float)):
        raise IdeStateSchemaError(
            "timestamp ausente ou não numérico em usageState",
            observed_keys=sorted(usage_state.keys()),
        )

    def _f(key: str, default: float = 0.0) -> float:
        v = b.get(key, default)
        try:
            return float(v) if v is not None else default
        except (TypeError, ValueError):
            return default

    return IdeUsageState(
        current_usage=_f("currentUsage"),
        usage_limit=_f("usageLimit"),
        percentage_used=_f("percentageUsed"),
        current_overages=_f("currentOverages"),
        overage_cap=_f("overageCap"),
        overage_charges=_f("overageCharges"),
        overage_rate=_f("overageRate"),
        reset_date=_parse_iso_utc(str(b["resetDate"])),
        currency_code=str(currency.get("code", "")),
        currency_symbol=str(currency.get("symbol", "")),
        unit=str(b.get("unit", "")),
        type=str(b.get("type", "")),
        timestamp=_ms_to_dt_utc(timestamp_ms),
        schema_version_observed=1,
    )


class IdeStateBackend(Backend):
    """Backend para o ``state.vscdb`` do Kiro IDE (chave ``kiro.kiroAgent``).

    Parâmetros
    ----------
    db_path
        Override do path do ``state.vscdb``. Default:
        :data:`DEFAULT_IDE_STATE_VSCDB`.
    """

    def __init__(self, db_path: Path | None = None):
        self._db_path = db_path or DEFAULT_IDE_STATE_VSCDB

    @property
    def slug(self) -> str:
        return "ide"

    @property
    def db_path(self) -> Path:
        return self._db_path

    def capabilities(self) -> set[Capability]:
        return {Capability.USAGE_STATE}

    def is_available(self) -> bool:
        """``True`` se o ``state.vscdb`` existir e tiver schema reconhecido."""
        try:
            state = self.read_usage_state()
        except IdeStateError:
            return False
        return state is not None

    def read_usage_state(self) -> IdeUsageState | None:
        """Lê e parseia o billing autoritativo.

        Retorna ``None`` se o arquivo não existe ou se não tem a chave
        ``kiro.kiroAgent`` (IDE não foi aberto ou versão incompatível).
        Levanta :exc:`IdeStateSchemaError` se a chave existe mas o shape
        é desconhecido (mudança de schema entre versões).
        """
        payload = _read_kiro_agent_blob(self._db_path)
        if payload is None:
            return None
        return _parse_usage_state(payload)

    def data_age(self) -> float | None:
        """Idade (s) do snapshot mais recente; ``None`` se indisponível."""
        try:
            state = self.read_usage_state()
        except IdeStateError:
            return None
        if state is None:
            return None
        return state.age_seconds
