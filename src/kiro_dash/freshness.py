"""Classificação visual de frescor de dados (ADR-0001 §"Política de frescor").

Convenção de cores e thresholds (defaults do ADR-0001):

- ``GREEN``: idade < 3h
- ``YELLOW``: 3h ≤ idade < 12h
- ``RED``: 12h ≤ idade < 24h
- ``GRAY``: idade ≥ 24h (saldo "fora de operação útil")

Thresholds são configuráveis via seção ``[freshness]`` do
``~/.config/kiro-dash/config.toml``; este módulo só conhece a função
matemática de classificação e helpers de formatação.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FreshnessLevel(Enum):
    """Faixa visual de frescor de um dado cacheado."""

    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"
    GRAY = "gray"


@dataclass(frozen=True, slots=True)
class FreshnessThresholds:
    """Limiares de classificação por faixa, em horas.

    Os limites são **superiores** (exclusivos). Uma idade de exatamente
    3h cai em ``YELLOW`` (ADR-0001 §"Política de frescor"; interpretação
    confirmada com Léo em 2026-05-27).
    """

    green_max_hours: float = 3.0
    yellow_max_hours: float = 12.0
    red_max_hours: float = 24.0


DEFAULT_THRESHOLDS = FreshnessThresholds()


def freshness_for(
    age_seconds: float,
    thresholds: FreshnessThresholds = DEFAULT_THRESHOLDS,
) -> FreshnessLevel:
    """Classifica idade (s) em :class:`FreshnessLevel`.

    Negativo ou zero → ``GREEN`` (acabou de atualizar / clock skew leve).
    """
    age_h = max(age_seconds, 0.0) / 3600.0
    if age_h < thresholds.green_max_hours:
        return FreshnessLevel.GREEN
    if age_h < thresholds.yellow_max_hours:
        return FreshnessLevel.YELLOW
    if age_h < thresholds.red_max_hours:
        return FreshnessLevel.RED
    return FreshnessLevel.GRAY


def format_age(age_seconds: float) -> str:
    """Humaniza segundos em ``"45s"`` / ``"3m"`` / ``"2h"`` / ``"1d"``.

    Negativo é normalizado para zero (``"0s"``).
    """
    s = max(int(age_seconds), 0)
    if s < 60:
        return f"{s}s"
    minutes, _ = divmod(s, 60)
    if minutes < 60:
        return f"{minutes}m"
    hours, _ = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h"
    days, _ = divmod(hours, 24)
    return f"{days}d"


def format_freshness_badge(
    level: FreshnessLevel,
    age_seconds: float,
    *,
    with_color: bool = True,
) -> str:
    """Formata badge ``[verde · 47s atrás]`` com (ou sem) markup rich.

    Quando ``with_color=True``, retorna string com tags rich
    (``[green]...[/green]``) prontas para ``rich.console.Console.print``.
    Quando ``False``, retorna texto puro.
    """
    label_pt = {
        FreshnessLevel.GREEN: "verde",
        FreshnessLevel.YELLOW: "amarelo",
        FreshnessLevel.RED: "vermelho",
        FreshnessLevel.GRAY: "cinza",
    }[level]
    age_text = format_age(age_seconds)
    text = f"{label_pt} · {age_text} atrás"
    if not with_color:
        return f"[{text}]"
    return f"[{level.value}]\\[{text}][/{level.value}]"


def freshness_message(level: FreshnessLevel, age_seconds: float) -> str:
    """Mensagem complementar do ADR-0001 conforme faixa.

    - GREEN: vazio
    - YELLOW: ``snapshot de Xh atrás``
    - RED: ``snapshot de Xh atrás — abra o Kiro IDE para refresh``
    - GRAY: ``snapshot stale (Xd) — saldo pode estar muito desatualizado``
    """
    age_text = format_age(age_seconds)
    if level is FreshnessLevel.GREEN:
        return ""
    if level is FreshnessLevel.YELLOW:
        return f"snapshot de {age_text} atrás"
    if level is FreshnessLevel.RED:
        return f"snapshot de {age_text} atrás — abra o Kiro IDE para refresh"
    return f"snapshot stale ({age_text}) — saldo pode estar muito desatualizado"
