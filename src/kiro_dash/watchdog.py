"""Detector de sessões running/stuck e operações de kill.

Sem hooks, sem root: fonte de verdade são os arquivos ``.json`` (turn
metadata) + ``.lock`` (PID + started_at) que o Kiro CLI grava em
``~/.kiro/sessions/cli/``.

Definições:

- *Running*: sessão tem lockfile válido E último turn com
  ``end_timestamp is None`` (turn em curso).
- *Stuck*: running cujo ``started_at`` do lockfile está mais antigo que
  ``threshold_secs``.
"""
from __future__ import annotations

import os
import signal
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from kiro_dash.models import LockInfo, Session
from kiro_dash.parser import read_lock


def is_session_running(session: Session) -> bool:
    """True quando há lock E último turn está em curso."""
    if not session.is_active:
        return False
    if not session.turns:
        return False
    return session.turns[-1].end_timestamp is None


def running_sessions(sessions: list[Session]) -> list[Session]:
    """Filtra sessões com turn em curso."""
    return [s for s in sessions if is_session_running(s)]


def stuck_sessions(
    sessions: list[Session],
    *,
    threshold_secs: int = 600,
    sessions_dir: Path | None = None,
    now: datetime | None = None,
) -> list[tuple[Session, LockInfo]]:
    """Running com ``started_at`` mais antigo que ``threshold_secs``."""
    n = now or datetime.now(timezone.utc)
    out: list[tuple[Session, LockInfo]] = []
    for s in running_sessions(sessions):
        info = read_lock(s.session_id, sessions_dir=sessions_dir)
        if info is None:
            continue
        age = (n - info.started_at).total_seconds()
        if age >= threshold_secs:
            out.append((s, info))
    return out


# ─── kill ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class KillResult:
    sid: str
    pid: int
    signal: str  # "SIGTERM" | "SIGKILL"
    ok: bool
    error: str | None = None


def kill_pid(pid: int, sig: int = signal.SIGTERM) -> tuple[bool, str | None]:
    """Tenta ``os.kill(pid, sig)``. Retorna (ok, error_msg)."""
    try:
        os.kill(pid, sig)
        return True, None
    except ProcessLookupError:
        return False, f"PID {pid} não existe"
    except PermissionError:
        return False, f"Sem permissão para matar PID {pid}"
    except OSError as exc:
        return False, str(exc)


def kill_session(
    sid: str,
    *,
    sig: int = signal.SIGTERM,
    sessions_dir: Path | None = None,
) -> KillResult:
    """Lê o lockfile da sessão e mata o PID com o sinal indicado."""
    info = read_lock(sid, sessions_dir=sessions_dir)
    if info is None:
        return KillResult(sid=sid, pid=0, signal=_signal_name(sig), ok=False,
                          error="Lockfile ausente")
    ok, err = kill_pid(info.pid, sig)
    return KillResult(sid=sid, pid=info.pid, signal=_signal_name(sig),
                      ok=ok, error=err)


def _signal_name(sig: int) -> str:
    return {signal.SIGTERM: "SIGTERM", signal.SIGKILL: "SIGKILL"}.get(sig, str(sig))
