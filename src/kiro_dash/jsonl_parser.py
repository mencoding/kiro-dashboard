"""Parser de arquivos transcript ``.jsonl`` do Kiro CLI.

**Princípio de privacidade:** este módulo é cego para conteúdo de
mensagens. Nunca expõe campos ``text``, ``thinking``, ``input`` de
toolUse, nem ``content`` de toolResult — apenas metadata estrutural
(nome da tool, id do uso, status).
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

ERROR_SUMMARY_MAX_LEN = 200


@dataclass(frozen=True, slots=True)
class ToolCall:
    """Uma chamada de ferramenta dentro de um transcript."""

    name: str
    tool_use_id: str
    status: str  # "success" | "error" | "unknown"
    session_id: str
    input_keys: list[str] = field(default_factory=list)
    error_summary: str | None = None


def _summarize_error(content: object) -> str | None:
    """Primeira linha não-vazia, capped em 200 chars."""
    if content is None:
        return None
    if isinstance(content, list):
        text = " ".join(
            str(c.get("data", c) if isinstance(c, dict) else c) for c in content
        )
    else:
        text = str(content)
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line[:ERROR_SUMMARY_MAX_LEN]
    return text[:ERROR_SUMMARY_MAX_LEN] or None


from kiro_dash.cache import jsonl_cache


def iter_tool_calls(path: Path) -> Iterator[ToolCall]:
    """Itera ``ToolCall`` extraídos do transcript em ``path``.

    Cache mtime-based. Sessões com ``.lock`` bypassam cache.
    """
    if not path.is_file():
        return

    lock = path.with_suffix(".lock")
    is_active = lock.exists()

    if not is_active:
        cached = jsonl_cache().get(path)
        if cached is not None:
            for c in cached:
                yield ToolCall(**c)
            return

    session_id = path.stem
    tool_uses: list[tuple[str, str, list[str]]] = []  # (name, id, input_keys)
    statuses: dict[str, str] = {}
    error_summaries: dict[str, str | None] = {}

    try:
        with path.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except (json.JSONDecodeError, TypeError):
                    continue
                if not isinstance(obj, dict):
                    continue
                kind = obj.get("kind")
                data = obj.get("data")
                if not isinstance(data, dict):
                    continue
                content = data.get("content")
                if not isinstance(content, list):
                    continue
                for item in content:
                    if not isinstance(item, dict):
                        continue
                    item_kind = item.get("kind")
                    item_data = item.get("data") or {}
                    if not isinstance(item_data, dict):
                        continue
                    if kind == "AssistantMessage" and item_kind == "toolUse":
                        name = item_data.get("name", "")
                        tu_id = item_data.get("toolUseId", "")
                        input_obj = item_data.get("input")
                        keys = list(input_obj.keys()) if isinstance(input_obj, dict) else []
                        if name and tu_id:
                            tool_uses.append((name, tu_id, keys))
                    elif kind == "ToolResults" and item_kind == "toolResult":
                        tu_id = item_data.get("toolUseId", "")
                        status = item_data.get("status", "")
                        if tu_id:
                            statuses[tu_id] = status or "unknown"
                            if status == "error":
                                error_summaries[tu_id] = _summarize_error(
                                    item_data.get("content")
                                )
    except OSError:
        return

    results = [
        ToolCall(
            name=name,
            tool_use_id=tu_id,
            status=statuses.get(tu_id, "unknown"),
            session_id=session_id,
            input_keys=keys,
            error_summary=error_summaries.get(tu_id),
        )
        for name, tu_id, keys in tool_uses
    ]

    if not is_active:
        jsonl_cache().put(
            path,
            [
                {
                    "name": t.name,
                    "tool_use_id": t.tool_use_id,
                    "status": t.status,
                    "session_id": t.session_id,
                    "input_keys": t.input_keys,
                    "error_summary": t.error_summary,
                }
                for t in results
            ],
        )

    yield from results
