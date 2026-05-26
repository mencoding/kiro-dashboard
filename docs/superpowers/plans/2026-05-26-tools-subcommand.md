# Wave 1 / Frente B — `tools` subcommand Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar `kiro-dash tools` que mostra breakdown agregado de chamadas de ferramentas (tool calls) numa janela temporal, lendo os arquivos `.jsonl` de transcript em `~/.kiro/sessions/cli/`.

**Architecture:** Novo módulo `jsonl_parser.py` com função geradora `iter_tool_calls(path)` que lê um `.jsonl` linha-a-linha e emite apenas eventos `kind="toolUse"`/`kind="toolResult"` — **deliberadamente cego para conteúdo** (`text`, `thinking`). Agregação agnóstica em `aggregator.py`. Subcomando Click reutilizando o esqueleto de tabela existente.

**Tech Stack:** Python 3.12, Click, Rich, pytest. Sem dependências novas (parsing JSON nativo).

**Branch:** `feat/wave1-tools`

**Schema verificado** (sessão real):
- Top-level kinds: `Prompt`, `AssistantMessage`, `ToolResults`
- Dentro de `data.content[]`: `text`, `thinking`, `toolUse`, `toolResult`
- `toolUse.data` tem `{name, toolUseId, input}` — usamos só `name` e `toolUseId`
- `toolResult.data` tem `{toolUseId, content}` — usamos só `toolUseId` para correlacionar com o `toolUse`

---

## File Structure

| Arquivo | Responsabilidade | Mudança |
|---|---|---|
| `src/kiro_dash/jsonl_parser.py` | Parser de transcript `.jsonl`, cego ao conteúdo | **Criar** |
| `src/kiro_dash/aggregator.py` | Agregações | **Modificar** — adicionar `aggregate_tools_in_window` |
| `src/kiro_dash/cli.py` | Subcomandos | **Modificar** — adicionar `tools` |
| `tests/fixtures/sample_session.jsonl` | Fixture mínimo de transcript | **Criar** |
| `tests/test_jsonl_parser.py` | Testes do parser | **Criar** |
| `tests/test_tools_command.py` | Smoke do CLI | **Criar** |

---

### Task 1: Fixture mínima de `.jsonl`

**Files:**
- Create: `tests/fixtures/sample_session.jsonl`

- [ ] **Step 1: Criar fixture com 1 prompt + 1 assistant message com 2 toolUse + 1 ToolResults com 2 toolResult**

Conteúdo (cada linha é um JSON; **cuidado: cada objeto deve estar em uma única linha**):

```jsonl
{"version":"v1","kind":"Prompt","data":{"content":[{"kind":"text","data":"Lê o README e lista os arquivos"}]}}
{"version":"v1","kind":"AssistantMessage","data":{"message_id":"m1","content":[{"kind":"thinking","data":{"text":"Vou ler e listar"}},{"kind":"text","data":"Vou ler o README e listar os arquivos."},{"kind":"toolUse","data":{"name":"read","toolUseId":"tu_001","input":{"path":"README.md"}}},{"kind":"toolUse","data":{"name":"glob","toolUseId":"tu_002","input":{"pattern":"*.py"}}}]}}
{"version":"v1","kind":"ToolResults","data":{"message_id":"m2","content":[{"kind":"toolResult","data":{"toolUseId":"tu_001","content":[{"kind":"text","data":"README content"}],"status":"success"}},{"kind":"toolResult","data":{"toolUseId":"tu_002","content":[{"kind":"text","data":"file1.py\nfile2.py"}],"status":"success"}}]}}
{"version":"v1","kind":"AssistantMessage","data":{"message_id":"m3","content":[{"kind":"text","data":"Encontrei dois arquivos."},{"kind":"toolUse","data":{"name":"read","toolUseId":"tu_003","input":{"path":"file1.py"}}}]}}
{"version":"v1","kind":"ToolResults","data":{"message_id":"m4","content":[{"kind":"toolResult","data":{"toolUseId":"tu_003","content":[{"kind":"text","data":"contents"}],"status":"error"}}]}}
```

5 linhas, 3 toolUse (`read`, `glob`, `read`) e 3 toolResult (2 success, 1 error).

- [ ] **Step 2: Commit**

```bash
cd /home/menzani/Desenvolvimento/mencoding/kiro-dash
git add tests/fixtures/sample_session.jsonl
git commit -m "test(fixtures): adicionar transcript .jsonl mínimo (3 toolUses)"
```

---

### Task 2: `iter_tool_calls` — parser principal

**Files:**
- Create: `src/kiro_dash/jsonl_parser.py`
- Create: `tests/test_jsonl_parser.py`

- [ ] **Step 1: Escrever os testes**

Criar `tests/test_jsonl_parser.py`:

```python
"""Testes do parser de transcript .jsonl — cego ao conteúdo."""
from __future__ import annotations

from pathlib import Path

from kiro_dash.jsonl_parser import ToolCall, iter_tool_calls

FIXTURE = Path(__file__).parent / "fixtures" / "sample_session.jsonl"


def test_iter_tool_calls_extracts_only_tool_use_events():
    calls = list(iter_tool_calls(FIXTURE))
    assert len(calls) == 3
    names = [c.name for c in calls]
    assert names == ["read", "glob", "read"]


def test_iter_tool_calls_correlates_status_from_tool_results():
    calls = list(iter_tool_calls(FIXTURE))
    # tu_001 success, tu_002 success, tu_003 error
    by_id = {c.tool_use_id: c.status for c in calls}
    assert by_id == {
        "tu_001": "success",
        "tu_002": "success",
        "tu_003": "error",
    }


def test_iter_tool_calls_does_not_expose_text_or_thinking():
    """Garante que NENHUM campo do retorno carrega conteúdo de mensagens."""
    calls = list(iter_tool_calls(FIXTURE))
    for c in calls:
        # Atributos do dataclass são fechados; garantimos que não foram smuggled
        # via dict/list. ToolCall só pode ter os campos abaixo.
        allowed = {"name", "tool_use_id", "status", "session_id"}
        assert set(c.__dataclass_fields__.keys()) == allowed


def test_iter_tool_calls_missing_file_returns_empty():
    calls = list(iter_tool_calls(Path("/tmp/nonexistent.jsonl")))
    assert calls == []


def test_iter_tool_calls_malformed_lines_skipped(tmp_path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text(
        '{"kind":"Prompt"}\n'
        'not-json\n'
        '{"kind":"AssistantMessage","data":{"content":[{"kind":"toolUse","data":{"name":"read","toolUseId":"x"}}]}}\n'
    )
    calls = list(iter_tool_calls(bad))
    assert len(calls) == 1
    assert calls[0].name == "read"
```

- [ ] **Step 2: Rodar — falha**

```bash
cd /home/menzani/Desenvolvimento/mencoding/kiro-dash
source .venv/bin/activate
pytest tests/test_jsonl_parser.py -v
```

Expected: ImportError (`kiro_dash.jsonl_parser` não existe).

- [ ] **Step 3: Implementar parser**

Criar `src/kiro_dash/jsonl_parser.py`:

```python
"""Parser de arquivos transcript ``.jsonl`` do Kiro CLI.

**Princípio de privacidade:** este módulo é cego para conteúdo de
mensagens. Nunca expõe campos ``text``, ``thinking``, ``input`` de
toolUse, nem ``content`` de toolResult — apenas metadata estrutural
(nome da tool, id do uso, status).

Schema (verificado em sessões reais, v1):

- Cada linha do ``.jsonl`` é um JSON ``{version, kind, data}``.
- ``kind`` top-level: ``Prompt``, ``AssistantMessage``, ``ToolResults``.
- Em ``AssistantMessage.data.content[]`` aparecem itens com kind
  ``text``, ``thinking``, ``toolUse``. Coletamos apenas ``toolUse``.
- Em ``ToolResults.data.content[]`` aparecem itens kind ``toolResult``.
  Coletamos apenas para correlacionar ``toolUseId`` -> status.
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ToolCall:
    """Uma chamada de ferramenta dentro de um transcript.

    ``status`` é resolvido cruzando o ``toolUseId`` com o
    ``toolResult`` correspondente; ``"unknown"`` quando o resultado
    não foi encontrado no mesmo arquivo (sessão ainda em andamento).
    """

    name: str
    tool_use_id: str
    status: str  # "success" | "error" | "unknown"
    session_id: str  # derivado do nome do arquivo (sem extensão)


def _safe_loads(line: str) -> dict | None:
    try:
        obj = json.loads(line)
    except (json.JSONDecodeError, TypeError):
        return None
    return obj if isinstance(obj, dict) else None


def iter_tool_calls(path: Path) -> Iterator[ToolCall]:
    """Itera ``ToolCall`` extraídos do transcript em ``path``.

    Faz duas passadas conceituais em UMA leitura:
    - Primeiro coleta todos os toolUse (em ordem).
    - Coleta status dos toolResult num dict ``{tool_use_id: status}``.
    - Emite os toolUse na ordem original com status correlacionado.

    Linhas malformadas / arquivos inexistentes -> iterador vazio.
    """
    if not path.is_file():
        return

    session_id = path.stem  # "<uuid>.jsonl" -> "<uuid>"

    tool_uses: list[tuple[str, str]] = []  # (name, tool_use_id) na ordem
    statuses: dict[str, str] = {}

    try:
        with path.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                obj = _safe_loads(line)
                if obj is None:
                    continue
                kind = obj.get("kind")
                data = obj.get("data") or {}
                content = data.get("content") if isinstance(data, dict) else None
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
                        name = str(item_data.get("name", "") or "")
                        tu_id = str(item_data.get("toolUseId", "") or "")
                        if name and tu_id:
                            tool_uses.append((name, tu_id))
                    elif kind == "ToolResults" and item_kind == "toolResult":
                        tu_id = str(item_data.get("toolUseId", "") or "")
                        status = str(item_data.get("status", "") or "")
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
```

- [ ] **Step 4: Rodar testes — passa**

```bash
pytest tests/test_jsonl_parser.py -v
```

Expected: 5 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/kiro_dash/jsonl_parser.py tests/test_jsonl_parser.py
git commit -m "feat(jsonl_parser): parser cego de transcript com correlação de status"
```

---

### Task 3: Agregação de tool calls em janela

**Files:**
- Modify: `src/kiro_dash/aggregator.py`
- Modify: `tests/test_aggregator.py` (criado em Frente A; se Frente A não rodou ainda, criar arquivo)

- [ ] **Step 1: Escrever teste**

Acrescentar em `tests/test_aggregator.py` (ou criar se não existir):

```python
from datetime import datetime, timedelta, timezone
from pathlib import Path

from kiro_dash.aggregator import aggregate_tools_in_window
from kiro_dash.jsonl_parser import ToolCall


def test_aggregate_tools_in_window_groups_by_name(tmp_path, monkeypatch):
    # Cria 2 .jsonl artificiais
    s1 = tmp_path / "11111111.jsonl"
    s2 = tmp_path / "22222222.jsonl"
    s1.write_text(
        '{"version":"v1","kind":"AssistantMessage","data":{"content":['
        '{"kind":"toolUse","data":{"name":"read","toolUseId":"a"}},'
        '{"kind":"toolUse","data":{"name":"shell","toolUseId":"b"}}'
        ']}}\n'
    )
    s2.write_text(
        '{"version":"v1","kind":"AssistantMessage","data":{"content":['
        '{"kind":"toolUse","data":{"name":"read","toolUseId":"c"}}'
        ']}}\n'
    )

    # mtime dos dois dentro da janela de 24h
    aggs = aggregate_tools_in_window(tmp_path, hours=24)
    by_name = {a["name"]: a for a in aggs}
    assert by_name["read"]["count"] == 2
    assert by_name["shell"]["count"] == 1
    assert by_name["read"]["sessions"] == 2
    assert by_name["shell"]["sessions"] == 1


def test_aggregate_tools_in_window_excludes_old_files(tmp_path):
    import os
    import time

    old = tmp_path / "old.jsonl"
    old.write_text(
        '{"version":"v1","kind":"AssistantMessage","data":{"content":['
        '{"kind":"toolUse","data":{"name":"read","toolUseId":"x"}}]}}\n'
    )
    # Mtime para 48h atrás
    past = time.time() - 48 * 3600
    os.utime(old, (past, past))

    aggs = aggregate_tools_in_window(tmp_path, hours=24)
    assert aggs == []
```

- [ ] **Step 2: Rodar — falha**

```bash
pytest tests/test_aggregator.py::test_aggregate_tools_in_window_groups_by_name -v
```

Expected: FAIL com `ImportError: aggregate_tools_in_window`.

- [ ] **Step 3: Implementar agregação**

Adicionar em `src/kiro_dash/aggregator.py`:

```python
import time
from collections import Counter, defaultdict
from pathlib import Path

from kiro_dash.jsonl_parser import iter_tool_calls


def aggregate_tools_in_window(
    sessions_dir: Path,
    *,
    hours: int = 24,
) -> list[dict]:
    """Conta tool calls em todos os ``.jsonl`` cujo mtime cai na janela.

    Usa o mtime do arquivo como proxy de "houve atividade nessa sessão na
    janela" — o transcript não tem timestamp por entry. Sessões cujo
    último append foi antes do cutoff são puladas inteiras.

    Retorna lista de dicts ``{name, count, sessions, errors}`` ordenada por
    ``count`` desc.
    """
    if not sessions_dir.is_dir():
        return []

    cutoff = time.time() - hours * 3600
    counts: Counter[str] = Counter()
    sessions_by_name: dict[str, set[str]] = defaultdict(set)
    errors_by_name: Counter[str] = Counter()

    for path in sessions_dir.iterdir():
        if not (path.is_file() and path.suffix == ".jsonl"):
            continue
        try:
            if path.stat().st_mtime < cutoff:
                continue
        except OSError:
            continue
        for call in iter_tool_calls(path):
            counts[call.name] += 1
            sessions_by_name[call.name].add(call.session_id)
            if call.status == "error":
                errors_by_name[call.name] += 1

    result = [
        {
            "name": name,
            "count": cnt,
            "sessions": len(sessions_by_name[name]),
            "errors": errors_by_name[name],
        }
        for name, cnt in counts.most_common()
    ]
    return result
```

- [ ] **Step 4: Rodar — passa**

```bash
pytest tests/test_aggregator.py -v
```

Expected: todos os testes do aggregator passam, incluindo os 2 novos.

- [ ] **Step 5: Commit**

```bash
git add src/kiro_dash/aggregator.py tests/test_aggregator.py
git commit -m "feat(aggregator): aggregate_tools_in_window via .jsonl + mtime"
```

---

### Task 4: Subcomando `tools`

**Files:**
- Modify: `src/kiro_dash/cli.py`
- Create: `tests/test_tools_command.py`

- [ ] **Step 1: Escrever teste smoke**

Criar `tests/test_tools_command.py`:

```python
"""Smoke do subcomando tools."""
from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from kiro_dash.cli import main


def test_tools_renders_table_when_data_available(tmp_path):
    j = tmp_path / "11111111.jsonl"
    j.write_text(
        '{"version":"v1","kind":"AssistantMessage","data":{"content":['
        '{"kind":"toolUse","data":{"name":"read","toolUseId":"a"}},'
        '{"kind":"toolUse","data":{"name":"shell","toolUseId":"b"}},'
        '{"kind":"toolUse","data":{"name":"read","toolUseId":"c"}}'
        ']}}\n'
    )
    with patch("kiro_dash.cli.DEFAULT_SESSIONS_DIR", tmp_path):
        runner = CliRunner()
        result = runner.invoke(main, ["tools", "--hours", "48"])
    assert result.exit_code == 0
    assert "read" in result.output
    assert "shell" in result.output


def test_tools_empty_window_shows_message(tmp_path):
    with patch("kiro_dash.cli.DEFAULT_SESSIONS_DIR", tmp_path):
        runner = CliRunner()
        result = runner.invoke(main, ["tools"])
    assert result.exit_code == 0
    assert "Nenhuma" in result.output or "Sem" in result.output
```

- [ ] **Step 2: Rodar — falha**

```bash
pytest tests/test_tools_command.py -v
```

Expected: FAIL `Error: No such command 'tools'`.

- [ ] **Step 3: Implementar comando**

Em `src/kiro_dash/cli.py`, adicionar import:

```python
from kiro_dash.aggregator import aggregate_tools_in_window
```

E o comando, antes do `if __name__ == "__main__"`:

```python
@main.command()
@click.option("--hours", default=24, type=int, help="Janela em horas (default 24).")
@click.option("--limit", default=20, type=int, help="Top N tools (default 20).")
def tools(hours: int, limit: int) -> None:
    """Breakdown de tool calls nas últimas N horas (lê .jsonl)."""
    aggs = aggregate_tools_in_window(DEFAULT_SESSIONS_DIR, hours=hours)
    if not aggs:
        console.print(f"[yellow]Nenhuma tool call nas últimas {hours}h.[/yellow]")
        return

    aggs = aggs[:limit]
    total = sum(a["count"] for a in aggs)
    err_total = sum(a["errors"] for a in aggs)

    header = Text()
    header.append(f"últimas {hours}h  ", style="bold")
    header.append(f"{total} chamadas", style="bold cyan")
    if err_total:
        header.append(f"  {err_total} erros", style="bold red")
    console.print(Panel(header, title="Tools", expand=False))

    table = Table(title="Tools", expand=False, header_style="bold")
    table.add_column("tool")
    table.add_column("count", justify="right")
    table.add_column("sessões", justify="right")
    table.add_column("erros", justify="right")
    for a in aggs:
        err_cell = Text(str(a["errors"]), style="red") if a["errors"] else Text("0", style="dim")
        table.add_row(a["name"], str(a["count"]), str(a["sessions"]), err_cell)
    console.print(table)
```

- [ ] **Step 4: Rodar — passa**

```bash
pytest tests/test_tools_command.py -v
```

Expected: 2 PASSED.

- [ ] **Step 5: Smoke manual**

```bash
kiro-dash tools
kiro-dash tools --hours 1
kiro-dash tools --hours 168 --limit 5
```

Expected: tabela com tools (read, shell, write, etc.), counts plausíveis, erros realçados em vermelho.

- [ ] **Step 6: Commit**

```bash
git add src/kiro_dash/cli.py tests/test_tools_command.py
git commit -m "feat(cli): subcomando tools com janela --hours e --limit"
```

---

## Self-Review Checklist

- [ ] `ToolCall` só tem 4 campos: `name`, `tool_use_id`, `status`, `session_id` — nada de `input`, `text`, `thinking`, `content`
- [ ] Parser nunca lê `data` de `text`/`thinking`/`toolResult.content`/`toolUse.input`
- [ ] Mensagens malformadas / arquivos inexistentes não derrubam — retornam vazio
- [ ] `aggregate_tools_in_window` filtra por mtime corretamente
- [ ] Teste explícito de privacidade (`test_iter_tool_calls_does_not_expose_text_or_thinking`) garante invariante
- [ ] Subcomando aceita `--hours` e `--limit`
- [ ] Erros realçados em vermelho

## Done When

- `pytest tests/test_jsonl_parser.py tests/test_tools_command.py tests/test_aggregator.py -v` → todos passam
- `kiro-dash tools --hours 24` rende output coerente (top tools daquele dia)
- 4 commits no branch `feat/wave1-tools`
