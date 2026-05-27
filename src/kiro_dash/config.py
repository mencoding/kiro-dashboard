"""Configuração persistente em ``~/.config/kiro-dash/config.toml``."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import tomli_w

VALID_TIERS = {"free", "pro", "pro+", "power", "enterprise"}

DEFAULT_MONTHLY_CREDITS: dict[str, int] = {
    "free": 50,
    "pro": 1000,
    "pro+": 2000,
    "power": 10000,
    "enterprise": 99_999_999,
}


@dataclass(frozen=True, slots=True)
class PlanConfig:
    """Plano declarado pelo usuário."""

    tier: str
    monthly_credits: int
    cycle_start: date


def default_config_path() -> Path:
    """``$XDG_CONFIG_HOME/kiro-dash/config.toml`` ou ``~/.config/kiro-dash/config.toml``."""
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / "kiro-dash" / "config.toml"


def _today_first() -> date:
    return date.today().replace(day=1)


def load_plan(path: Path | None = None) -> PlanConfig:
    """Carrega plano do TOML. Arquivo ausente → default ``free``."""
    if path is None:
        path = default_config_path()

    if not path.is_file():
        return PlanConfig(tier="free", monthly_credits=50, cycle_start=_today_first())

    try:
        with path.open("rb") as f:
            raw = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return PlanConfig(tier="free", monthly_credits=50, cycle_start=_today_first())

    plan_data = raw.get("plan", {}) if isinstance(raw, dict) else {}
    tier = str(plan_data.get("tier", "free")).strip().lower()
    if tier not in VALID_TIERS:
        tier = "free"

    monthly_credits = plan_data.get("monthly_credits")
    if not isinstance(monthly_credits, int) or monthly_credits <= 0:
        monthly_credits = DEFAULT_MONTHLY_CREDITS[tier]

    cycle_raw = plan_data.get("cycle_start")
    if isinstance(cycle_raw, date):
        cycle_start = cycle_raw
    elif isinstance(cycle_raw, str):
        try:
            cycle_start = date.fromisoformat(cycle_raw)
        except ValueError:
            cycle_start = _today_first()
    else:
        cycle_start = _today_first()

    return PlanConfig(tier=tier, monthly_credits=monthly_credits, cycle_start=cycle_start)


def save_plan(plan: PlanConfig, path: Path | None = None) -> None:
    """Persiste o plano em TOML, criando diretórios pais se necessário."""
    if path is None:
        path = default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "plan": {
            "tier": plan.tier,
            "monthly_credits": plan.monthly_credits,
            "cycle_start": plan.cycle_start,
        }
    }
    with path.open("wb") as f:
        tomli_w.dump(data, f)
