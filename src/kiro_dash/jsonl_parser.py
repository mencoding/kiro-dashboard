"""Parser de arquivos transcript ``.jsonl`` do Kiro CLI.

**Princípio de privacidade:** este módulo é cego para conteúdo de
mensagens. Nunca expõe campos ``text``, ``thinking``, ``input`` de
toolUse, nem ``content`` de toolResult — apenas metadata estrutural
(nome da tool, id do uso, status).
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ToolCall:
    """Uma chamada de ferramenta dentro de um transcript."""

    name: str
    tool_use_id: str
    status: str  # "success" | "error" | "unknown"
    session_id: str


def iter_tool_calls(path: Path) -> Iterator[ToolCall]:
    """Itera ``ToolCall`` extraídos do transcript em ``path``."""
    if not path.is_file():
        return

    session_id = path.stem
    tool_uses: list[tuple[str, str]] = []
    statuses: dict[str, str] = {}

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
                        if name and tu_id:
                            tool_uses.append((name, tu_id))
                    elif kind == "ToolResults" and item_kind == "toolResult":
                        tu_id = item_data.get("toolUseId", "")
                        status = item_data.get("status", "")
                        if tu_id:
                            statuses[tu_id] = status or "unknown"
    except OSError:
        return

    for name, tu_id in tool_uses:
        yield ToolCall(
            name=name,
            tool_use_id=tu_id,
            status=statuses.get(tu_id, "unknown"),
            session_id=session_id,
        )
