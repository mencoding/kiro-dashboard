"""Banner de onboarding sugerindo Kiro IDE quando só CLI detectado.

Comportamento (ADR-0001 §"Política de fallback"):

- Aparece **uma vez por dia** em comandos relevantes (``balance``,
  ``plan get``, primeiro ``today`` do dia)
- Estado em ``~/.cache/kiro-dash/banner_state.json``
- Suprimível via ``KIRO_DASH_NO_BANNER=1``

Mensagem em pt-BR. Sem ANSI cores aqui — quem chama decide formatação
(rich Console se for CLI).
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

BANNER_KEY_IDE_INSTALL = "ide_install"
"""Identificador do banner; permite múltiplos no futuro."""


def banner_state_path() -> Path:
    """``~/.cache/kiro-dash/banner_state.json`` (respeita ``$XDG_CACHE_HOME``)."""
    base = os.environ.get("XDG_CACHE_HOME")
    root = Path(base) if base else Path.home() / ".cache"
    return root / "kiro-dash" / "banner_state.json"


def _load_state(path: Path | None = None) -> dict:
    p = path or banner_state_path()
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(state: dict, path: Path | None = None) -> None:
    p = path or banner_state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        p.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except OSError:
        pass  # cache é best-effort; falha silenciosa não pode quebrar comando


def _today_key(now: datetime | None = None) -> str:
    n = now if now is not None else datetime.now(timezone.utc)
    return n.astimezone().date().isoformat()


def is_banner_suppressed_by_env() -> bool:
    """``True`` se ``KIRO_DASH_NO_BANNER=1`` está definida."""
    return os.environ.get("KIRO_DASH_NO_BANNER", "").strip() == "1"


def should_show_ide_banner(
    *,
    has_only_cli: bool,
    now: datetime | None = None,
    state_path: Path | None = None,
) -> bool:
    """Decide se o banner do IDE deve aparecer nesta execução.

    Critérios (todos têm que passar):

    1. ``has_only_cli=True`` (passado pelo caller a partir de ``Sources``)
    2. ``KIRO_DASH_NO_BANNER`` não está em ``"1"``
    3. Não foi mostrado hoje (estado em
       ``~/.cache/kiro-dash/banner_state.json``)
    """
    if not has_only_cli:
        return False
    if is_banner_suppressed_by_env():
        return False
    state = _load_state(state_path)
    last = state.get(BANNER_KEY_IDE_INSTALL, {}).get("last_shown")
    if last == _today_key(now):
        return False
    return True


def mark_ide_banner_shown(
    *,
    now: datetime | None = None,
    state_path: Path | None = None,
) -> None:
    """Registra que o banner foi exibido hoje."""
    state = _load_state(state_path)
    state.setdefault(BANNER_KEY_IDE_INSTALL, {})["last_shown"] = _today_key(now)
    _save_state(state, state_path)


def format_ide_banner_text() -> str:
    """Texto do banner em pt-BR (sem markup rich, sem cores)."""
    return (
        "ℹ️  Saldo de créditos é estimativa local (impreciso após uso "
        "cross-device).\n"
        "    Instale o Kiro IDE para saldo autoritativo do servidor:\n"
        "    https://kiro.dev/downloads/\n"
        "    Suprima este aviso com KIRO_DASH_NO_BANNER=1."
    )
