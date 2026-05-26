"""Fábricas de Session/Turn para testes — sem leitura de disco."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from kiro_dash.models import Session, Turn


def make_turn(
    *,
    end_timestamp: datetime,
    agent_name: str = "kiro_default",
    parent_agent_id: str | None = None,
    duration_seconds: float = 1.0,
    end_reason: str = "UserTurnEnd",
    builtin_tool_uses: int = 0,
    number_of_cycles: int = 0,
    context_usage_pct: float = 0.0,
    credits: float = 0.1,
) -> Turn:
    return Turn(
        end_timestamp=end_timestamp,
        agent_name=agent_name,
        parent_agent_id=parent_agent_id,
        duration=timedelta(seconds=duration_seconds),
        end_reason=end_reason,
        builtin_tool_uses=builtin_tool_uses,
        number_of_cycles=number_of_cycles,
        context_usage_pct=context_usage_pct,
        credits=credits,
    )


def make_session(
    *,
    session_id: str = "11111111-1111-1111-1111-111111111111",
    title: str | None = "test session",
    agent_name: str = "kiro_default",
    model_id: str = "claude-opus-4.7",
    rate_multiplier: float = 2.2,
    context_window_tokens: int = 1_000_000,
    cwd: str = "/tmp/test",
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
    version: str = "v1",
    session_created_reason: str | None = None,
    is_active: bool = False,
    turns: list[Turn] | None = None,
) -> Session:
    now = datetime.now(timezone.utc)
    return Session(
        session_id=session_id,
        title=title,
        agent_name=agent_name,
        model_id=model_id,
        rate_multiplier=rate_multiplier,
        context_window_tokens=context_window_tokens,
        cwd=cwd,
        created_at=created_at or now - timedelta(hours=1),
        updated_at=updated_at or now,
        version=version,
        session_created_reason=session_created_reason,
        is_active=is_active,
        turns=turns or [],
    )
