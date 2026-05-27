"""Cache de leitura para parser, mtime/size-invalidated.

Cache em ``~/.cache/kiro-dash/`` (ou ``$XDG_CACHE_HOME/kiro-dash/``).
Cada entrada armazena ``{path, mtime_ns, size, payload}``. Hit válido
exige match exato dos 3 primeiros.

Bypass via ``KIRO_DASH_NO_CACHE=1`` no env.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def cache_dir_default() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "kiro-dash"


def _key_for(path: Path) -> str:
    return hashlib.sha256(str(path.resolve()).encode()).hexdigest()


def _disabled() -> bool:
    return os.environ.get("KIRO_DASH_NO_CACHE", "") == "1"


@dataclass(slots=True)
class SessionsCache:
    root: Path

    def __post_init__(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def _entry_path(self, src: Path) -> Path:
        return self.root / f"{_key_for(src)}.json"

    def get(self, src: Path) -> Any | None:
        if _disabled():
            return None
        if not src.exists():
            return None
        ep = self._entry_path(src)
        if not ep.exists():
            return None
        try:
            with open(ep) as f:
                entry = json.load(f)
        except (OSError, json.JSONDecodeError):
            return None
        st = src.stat()
        if (
            entry.get("path") != str(src.resolve())
            or entry.get("mtime_ns") != st.st_mtime_ns
            or entry.get("size") != st.st_size
        ):
            return None
        return entry.get("payload")

    def put(self, src: Path, payload: Any) -> None:
        if _disabled():
            return
        if not src.exists():
            return
        st = src.stat()
        entry = {
            "path": str(src.resolve()),
            "mtime_ns": st.st_mtime_ns,
            "size": st.st_size,
            "payload": payload,
        }
        ep = self._entry_path(src)
        try:
            with open(ep, "w") as f:
                json.dump(entry, f)
        except OSError:
            pass

    def clear(self) -> int:
        n = 0
        if not self.root.exists():
            return 0
        for p in self.root.glob("*.json"):
            try:
                p.unlink()
                n += 1
            except OSError:
                pass
        return n

    def info(self) -> dict[str, int]:
        n, total = 0, 0
        if not self.root.exists():
            return {"entries": 0, "bytes": 0}
        for p in self.root.glob("*.json"):
            try:
                total += p.stat().st_size
                n += 1
            except OSError:
                pass
        return {"entries": n, "bytes": total}


# ─── singletons ──────────────────────────────────────────────────────────

_sessions_cache: SessionsCache | None = None
_jsonl_cache: SessionsCache | None = None


def sessions_cache() -> SessionsCache:
    global _sessions_cache
    if _sessions_cache is None:
        _sessions_cache = SessionsCache(root=cache_dir_default() / "sessions")
    return _sessions_cache


def jsonl_cache() -> SessionsCache:
    global _jsonl_cache
    if _jsonl_cache is None:
        _jsonl_cache = SessionsCache(root=cache_dir_default() / "jsonl")
    return _jsonl_cache


def clear_cache() -> dict[str, int]:
    return {
        "sessions": sessions_cache().clear(),
        "jsonl": jsonl_cache().clear(),
    }


def cache_info() -> dict[str, dict[str, int]]:
    return {
        "sessions": sessions_cache().info(),
        "jsonl": jsonl_cache().info(),
    }
