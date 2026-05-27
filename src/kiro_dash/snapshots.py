"""Snapshots diários de uso — persistência histórica.

Storage: ``~/.local/share/kiro-dash/snapshots/<YYYY-MM-DD>.<host>.json``.
"""
from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from kiro_dash.aggregator import (
    _resolve_now,
    aggregate_by_agent_pair,
    aggregate_by_model,
    aggregate_by_project,
    aggregate_by_session,
    aggregate_tools_in_window,
    total_credits,
    turns_in_local_day,
)
from kiro_dash.config import default_config_path, load_aliases
from kiro_dash.models import Session

SCHEMA_VERSION = 1


def snapshots_dir_default() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "kiro-dash" / "snapshots"


@dataclass(frozen=True, slots=True)
class SnapshotPaths:
    root: Path

    def for_date(self, d: date, host: str) -> Path:
        return self.root / f"{d.isoformat()}.{host}.json"

    def glob_for_date(self, d: date) -> list[Path]:
        if not self.root.exists():
            return []
        return sorted(self.root.glob(f"{d.isoformat()}.*.json"))


def _hostname() -> str:
    return socket.gethostname() or "unknown"


def build_snapshot(
    sessions: list[Session],
    *,
    d: date,
    host: str | None = None,
    now: datetime | None = None,
) -> dict:
    """Constrói dict do snapshot para ``d`` (data local). Não toca disco."""
    pairs = turns_in_local_day(sessions, d, now=now)
    aliases = load_aliases(default_config_path())

    sessions_dir = Path.home() / ".kiro" / "sessions" / "cli"
    tools = aggregate_tools_in_window(sessions_dir, hours=48)

    n = _resolve_now(now)
    tz_local = datetime.now().astimezone().tzinfo
    offset = tz_local.utcoffset(datetime.now())
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    h, m = divmod(abs(total_minutes), 60)
    tz_str = f"{sign}{h:02d}:{m:02d}"

    return {
        "schema_version": SCHEMA_VERSION,
        "local_date": d.isoformat(),
        "tz_offset": tz_str,
        "captured_at": n.isoformat().replace("+00:00", "Z"),
        "captured_by_host": host or _hostname(),
        "totals": {
            "credits": round(total_credits(pairs), 4),
            "turns": len(pairs),
            "sessions": len({s.session_id for s, _ in pairs}),
        },
        "by_model": [_agg_dict(a) for a in aggregate_by_model(pairs)],
        "by_project": [_agg_dict(a) for a in aggregate_by_project(pairs, aliases=aliases)],
        "by_agent_pair": [_pair_dict(a) for a in aggregate_by_agent_pair(pairs)],
        "by_session": [_agg_dict(a) for a in aggregate_by_session(pairs)],
        "by_tool": [
            {"name": t["name"], "count": t["count"], "sessions": t["sessions"], "errors": t["errors"]}
            for t in tools
        ],
    }


def _agg_dict(a) -> dict:
    return {
        "label": a.label,
        "credits": round(a.credits, 4),
        "turns": a.turns,
        "sessions": a.sessions,
        "duration_secs": int(a.duration.total_seconds()),
        "tool_uses": a.tool_uses,
    }


def _pair_dict(a) -> dict:
    return {
        "runtime": a.runtime,
        "persona": a.persona,
        "credits": round(a.credits, 4),
        "turns": a.turns,
        "sessions": a.sessions,
        "duration_secs": int(a.duration.total_seconds()),
        "tool_uses": a.tool_uses,
    }


def write_snapshot(
    sessions: list[Session],
    *,
    d: date,
    host: str | None = None,
    paths: SnapshotPaths | None = None,
    now: datetime | None = None,
    overwrite: bool = False,
) -> Path:
    """Constrói e grava snapshot. Retorna path criado."""
    p = paths or SnapshotPaths(root=snapshots_dir_default())
    p.root.mkdir(parents=True, exist_ok=True)
    h = host or _hostname()
    target = p.for_date(d, h)
    if target.exists() and not overwrite:
        return target
    snap = build_snapshot(sessions, d=d, host=h, now=now)
    with open(target, "w") as f:
        json.dump(snap, f, indent=2)
    return target


def read_snapshot(d: date, *, paths: SnapshotPaths | None = None) -> dict | None:
    """Lê e merge todos os snapshots do dia ``d`` (todos os hosts)."""
    p = paths or SnapshotPaths(root=snapshots_dir_default())
    files = p.glob_for_date(d)
    if not files:
        return None
    snaps = []
    for fp in files:
        try:
            with open(fp) as f:
                snaps.append(json.load(f))
        except (OSError, json.JSONDecodeError):
            continue
    if not snaps:
        return None
    if len(snaps) == 1:
        return snaps[0]
    return _merge_snapshots(snaps)


def _merge_snapshots(snaps: list[dict]) -> dict:
    out = {
        "schema_version": SCHEMA_VERSION,
        "local_date": snaps[0]["local_date"],
        "tz_offset": snaps[0]["tz_offset"],
        "captured_at": max(s["captured_at"] for s in snaps),
        "merged_from": [s["captured_by_host"] for s in snaps],
        "totals": {
            "credits": round(sum(s["totals"]["credits"] for s in snaps), 4),
            "turns": sum(s["totals"]["turns"] for s in snaps),
            "sessions": sum(s["totals"]["sessions"] for s in snaps),
        },
    }
    for key in ("by_model", "by_project", "by_agent_pair", "by_session", "by_tool"):
        out[key] = [item for s in snaps for item in s.get(key, [])]
    return out


def ensure_snapshots_up_to(
    up_to: date,
    sessions: list[Session],
    *,
    paths: SnapshotPaths | None = None,
    host: str | None = None,
    now: datetime | None = None,
    lookback_days: int = 30,
) -> list[Path]:
    """Garante snapshots de ``up_to - lookback_days`` até ``up_to`` (inclusive).

    Self-healing: dias sem snapshot do host atual são gerados.
    Retorna lista de paths criados.
    """
    p = paths or SnapshotPaths(root=snapshots_dir_default())
    p.root.mkdir(parents=True, exist_ok=True)
    h = host or _hostname()

    created: list[Path] = []
    for offset in range(lookback_days, -1, -1):
        d = up_to - timedelta(days=offset)
        target = p.for_date(d, h)
        if target.exists():
            continue
        # build + write (write_snapshot checks existence too, but we already checked)
        snap = build_snapshot(sessions, d=d, host=h, now=now)
        # Only write if there were turns that day
        if snap["totals"]["turns"] == 0:
            continue
        p.root.mkdir(parents=True, exist_ok=True)
        with open(target, "w") as f:
            json.dump(snap, f, indent=2)
        created.append(target)
    return created
