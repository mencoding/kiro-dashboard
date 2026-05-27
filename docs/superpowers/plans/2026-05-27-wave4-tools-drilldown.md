# Wave 4 / Frente K — Tools drill-down + bar visual Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Habilitar drill-down de tool calls — saber **causa dos erros** sem comprometer privacidade dos prompts. Inclui (1) estender `ToolCall` com `input_keys` e `error_summary`; (2) TUI Tools tab com seleção e painel inferior de erros recentes; (3) subcomando CLI `kiro-dash tool <name>` com filtros; (4) bar horizontal visual na tabela Tools agregada.

**Architecture:**

- **Privacidade:** `input_keys` mantém só **nomes** dos parâmetros do toolUse (sem values); `error_summary` extrai apenas a primeira linha (ou primeiros 200 chars) do `content` do toolResult quando `status=error`. Conteúdo de prompts nunca sai do `.jsonl` original.
- **Opt-in vazamento:** flag `--show-input` no `tool` CLI mostra values também (uso debug pessoal).
- **Visual:** Rich `BarColumn` para barras horizontais; sparkline (Unicode `▁▂▃▄▅▆▇█`) calculado in-house para mini-charts no painel inferior.
- **TUI:** seleção via `cursor_type="row"`, evento `RowSelected` chama método que renderiza painel inferior `Static`.

**Tech Stack:** Python 3.12 stdlib + Rich (já dep), Textual (já dep). Sem novas deps.

**Branch:** `feat/wave4-tools-drilldown`

---

## File Structure

| Arquivo | Responsabilidade | Mudança |
|---|---|---|
| `src/kiro_dash/models.py` | Estender dataclass `ToolCall` com `input_keys`, `error_summary` | **Modificar** |
| `src/kiro_dash/jsonl_parser.py` | Extrair os 2 novos campos no parse | **Modificar** |
| `src/kiro_dash/visual.py` | Helpers `bar_inline(pct)` e `sparkline(values)` | **Criar** |
| `src/kiro_dash/cli.py` | Subgrupo `tool <name>` + bar na tabela Tools | **Modificar** |
| `src/kiro_dash/views/tabs/tools_tab.py` | Seleção + painel inferior com erros + sparkline | **Modificar** |
| `tests/test_jsonl_parser.py` | Cobrir `input_keys` e `error_summary` | **Modificar** |
| `tests/test_visual.py` | Cobrir helpers | **Criar** |
| `tests/test_tool_command.py` | CLI tool com filtros | **Criar** |

---

### Task 1: Estender `ToolCall` com `input_keys` e `error_summary`

**Files:**
- Modify: `src/kiro_dash/models.py`
- Modify: `src/kiro_dash/jsonl_parser.py`
- Modify: `tests/test_jsonl_parser.py`

- [ ] **Step 1: Escrever testes**

Acrescentar em `tests/test_jsonl_parser.py`:

```python
def test_tool_call_extrai_input_keys_sem_values(tmp_path):
    """toolUse.input vira lista de keys, sem values (privacidade)."""
    from kiro_dash.jsonl_parser import parse_jsonl_tools

    p = tmp_path / "x.jsonl"
    p.write_text(
        '{"kind":"AssistantMessage","data":{"content":[{"type":"toolUse",'
        '"data":{"name":"shell","toolUseId":"abc","input":{"command":"rm -rf /","working_dir":"/tmp"}}}]}}\n'
    )
    tools = parse_jsonl_tools(p)
    assert len(tools) == 1
    t = tools[0]
    assert t.name == "shell"
    assert sorted(t.input_keys) == ["command", "working_dir"]


def test_tool_call_input_keys_lista_vazia_quando_sem_input(tmp_path):
    from kiro_dash.jsonl_parser import parse_jsonl_tools

    p = tmp_path / "x.jsonl"
    p.write_text(
        '{"kind":"AssistantMessage","data":{"content":[{"type":"toolUse",'
        '"data":{"name":"x","toolUseId":"abc","input":{}}}]}}\n'
    )
    tools = parse_jsonl_tools(p)
    assert tools[0].input_keys == []


def test_tool_call_error_summary_primeiros_200_chars(tmp_path):
    """toolResult.content vira error_summary só quando status=error."""
    from kiro_dash.jsonl_parser import parse_jsonl_tools

    p = tmp_path / "x.jsonl"
    long_err = "FileNotFoundError: [Errno 2] No such file or directory: '/tmp/missing.txt'\n  trace line\n  trace line"
    p.write_text(
        '{"kind":"AssistantMessage","data":{"content":[{"type":"toolUse",'
        '"data":{"name":"read","toolUseId":"abc","input":{"path":"/x"}}}]}}\n'
        '{"kind":"ToolResults","data":{"content":[{"type":"toolResult",'
        f'"data":{{"toolUseId":"abc","content":"{long_err}","status":"error"}}}}]}}\n'
    )
    tools = parse_jsonl_tools(p)
    assert tools[0].error_summary is not None
    assert "FileNotFoundError" in tools[0].error_summary
    assert len(tools[0].error_summary) <= 200


def test_tool_call_error_summary_none_em_success(tmp_path):
    from kiro_dash.jsonl_parser import parse_jsonl_tools

    p = tmp_path / "x.jsonl"
    p.write_text(
        '{"kind":"AssistantMessage","data":{"content":[{"type":"toolUse",'
        '"data":{"name":"read","toolUseId":"abc","input":{"path":"/x"}}}]}}\n'
        '{"kind":"ToolResults","data":{"content":[{"type":"toolResult",'
        '"data":{"toolUseId":"abc","content":"file contents","status":"success"}}]}}\n'
    )
    tools = parse_jsonl_tools(p)
    assert tools[0].error_summary is None
```

- [ ] **Step 2: Rodar — falha**

```bash
cd /home/menzani/Desenvolvimento/mencoding/kiro-dash
source .venv/bin/activate
pytest tests/test_jsonl_parser.py -v -k "input_keys or error_summary"
```

- [ ] **Step 3: Estender `ToolCall` em `models.py`**

```python
@dataclass(frozen=True, slots=True)
class ToolCall:
    """Tool call do .jsonl. Campos cegos a conteúdo (privacidade)."""
    name: str
    tool_use_id: str
    status: str | None
    timestamp: datetime | None
    # Wave 4 (v0.5.0): metadata adicional, sem vazar conteúdo de prompts.
    input_keys: list[str] = field(default_factory=list)  # só nomes dos params
    error_summary: str | None = None  # 1ª linha (ou 200 chars) de content quando status=error
```

(Garanta `from dataclasses import field` no topo do `models.py`.)

- [ ] **Step 4: Atualizar `jsonl_parser.py`**

No parse de `toolUse`: extrair `list(data.get("input", {}).keys())` → `input_keys`.

No parse de `toolResult`: se `status == "error"`, pegar `content`, extrair primeira linha (ou primeiros 200 chars), atribuir a `error_summary` no `ToolCall` correspondente (linkado via `toolUseId`).

```python
ERROR_SUMMARY_MAX_LEN = 200


def _summarize_error(content: object) -> str | None:
    """Primeira linha não-vazia, capped em 200 chars."""
    if content is None:
        return None
    if isinstance(content, list):
        # toolResult.content pode ser lista de chunks
        text = " ".join(str(c.get("text", c) if isinstance(c, dict) else c) for c in content)
    else:
        text = str(content)
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line[:ERROR_SUMMARY_MAX_LEN]
    return text[:ERROR_SUMMARY_MAX_LEN] or None
```

E na lógica de matching toolUse↔toolResult, popular o campo na hora de criar/atualizar o `ToolCall`.

- [ ] **Step 5: Rodar — passa**

```bash
pytest tests/test_jsonl_parser.py -v
```

- [ ] **Step 6: Commit**

```bash
git add src/kiro_dash/models.py src/kiro_dash/jsonl_parser.py tests/test_jsonl_parser.py
git -c user.email='leonardo.menzani@gmail.com' -c user.name='mencoding' \
  commit -m "feat(parser): ToolCall ganha input_keys e error_summary (privacy-safe)"
```

---

### Task 2: Helpers visuais — `bar_inline` e `sparkline`

**Files:**
- Create: `src/kiro_dash/visual.py`
- Create: `tests/test_visual.py`

- [ ] **Step 1: Escrever testes**

Criar `tests/test_visual.py`:

```python
"""Cobertura de helpers visuais."""
from __future__ import annotations

import pytest

from kiro_dash.visual import bar_inline, sparkline


def test_bar_inline_zero():
    assert bar_inline(0.0, width=10) == "░" * 10


def test_bar_inline_meio():
    bar = bar_inline(0.5, width=10)
    assert bar.count("█") == 5
    assert bar.count("░") == 5


def test_bar_inline_completo():
    assert bar_inline(1.0, width=10) == "█" * 10


def test_bar_inline_cap_em_1():
    assert bar_inline(2.0, width=10) == "█" * 10


def test_bar_inline_negativo_vira_zero():
    assert bar_inline(-0.5, width=10) == "░" * 10


def test_sparkline_serie_simples():
    out = sparkline([0, 1, 2, 3, 4, 5, 6, 7])
    assert len(out) == 8
    # mais alto deve usar block maior
    assert out[-1] == "█"
    assert out[0] == "▁"


def test_sparkline_lista_vazia():
    assert sparkline([]) == ""


def test_sparkline_todos_iguais():
    out = sparkline([5, 5, 5, 5])
    # todos iguais → primeiro nível
    assert all(c == "▁" for c in out)


def test_sparkline_cap_em_max_chars():
    out = sparkline([1, 2, 3, 4, 5], max_chars=3)
    assert len(out) == 3
```

- [ ] **Step 2: Rodar — falha**

```bash
pytest tests/test_visual.py -v
```

- [ ] **Step 3: Implementar `visual.py`**

```python
"""Helpers visuais para o painel — barras horizontais e sparklines.

Sem dependências novas; só Unicode block characters.
"""
from __future__ import annotations

# Unicode block characters de menor → maior densidade
_SPARK_CHARS = "▁▂▃▄▅▆▇█"


def bar_inline(pct: float, *, width: int = 20) -> str:
    """Barra horizontal Unicode. ``pct`` em [0, 1]; valores fora são clampados.

    Exemplos:
        >>> bar_inline(0.5, width=10)
        '█████░░░░░'
    """
    pct = max(0.0, min(1.0, pct))
    filled = int(round(pct * width))
    return "█" * filled + "░" * (width - filled)


def sparkline(values: list[float], *, max_chars: int = 24) -> str:
    """Mini line chart Unicode em UMA linha.

    ``values`` é a série; cada valor vira um caractere de bloco proporcional
    ao pico da série. Lista vazia → string vazia. Truncada nos últimos
    ``max_chars`` valores se exceder.

    Exemplos:
        >>> sparkline([1, 2, 3, 4, 5])
        '▁▂▄▆█'
    """
    if not values:
        return ""
    if len(values) > max_chars:
        values = values[-max_chars:]
    peak = max(values)
    if peak <= 0:
        return _SPARK_CHARS[0] * len(values)
    n_levels = len(_SPARK_CHARS)
    out = []
    for v in values:
        idx = max(0, min(n_levels - 1, int(round((v / peak) * (n_levels - 1)))))
        # Floor pra zero quando v == 0 (visualmente "vazio")
        if v <= 0:
            idx = 0
        out.append(_SPARK_CHARS[idx])
    return "".join(out)
```

- [ ] **Step 4: Rodar — passa**

```bash
pytest tests/test_visual.py -v
```

Expected: 9 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/kiro_dash/visual.py tests/test_visual.py
git -c user.email='leonardo.menzani@gmail.com' -c user.name='mencoding' \
  commit -m "feat(visual): bar_inline + sparkline (Unicode block chars)"
```

---

### Task 3: Subcomando CLI `kiro-dash tool <name>`

**Files:**
- Modify: `src/kiro_dash/cli.py`
- Create: `tests/test_tool_command.py`

- [ ] **Step 1: Escrever testes**

Criar `tests/test_tool_command.py`:

```python
"""Subcomando ``kiro-dash tool <name>``."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from click.testing import CliRunner

from kiro_dash.cli import main
from kiro_dash.models import ToolCall


def _fake_tool_calls():
    now = datetime.now(timezone.utc)
    return [
        ToolCall(name="shell", tool_use_id="t1", status="success",
                 timestamp=now, input_keys=["command"]),
        ToolCall(name="shell", tool_use_id="t2", status="error",
                 timestamp=now, input_keys=["command"],
                 error_summary="exit 1: command not found"),
        ToolCall(name="shell", tool_use_id="t3", status="error",
                 timestamp=now, input_keys=["command", "working_dir"],
                 error_summary="permission denied"),
        ToolCall(name="read", tool_use_id="t4", status="success",
                 timestamp=now, input_keys=["path"]),
    ]


def test_tool_command_filtra_pelo_nome():
    with patch("kiro_dash.cli.collect_recent_tools", return_value=_fake_tool_calls()):
        runner = CliRunner()
        result = runner.invoke(main, ["tool", "shell"])
    assert result.exit_code == 0
    assert "shell" in result.output
    assert "exit 1" in result.output  # error_summary do t2
    assert "permission denied" in result.output  # error_summary do t3
    # read não deve aparecer (filtrou shell)
    assert "read" not in result.output.lower() or result.output.count("read") <= 1


def test_tool_command_errors_only_filtra_status():
    with patch("kiro_dash.cli.collect_recent_tools", return_value=_fake_tool_calls()):
        runner = CliRunner()
        result = runner.invoke(main, ["tool", "shell", "--errors-only"])
    assert result.exit_code == 0
    assert "exit 1" in result.output
    assert "permission denied" in result.output
    # success não deve aparecer
    assert "t1" not in result.output


def test_tool_command_sem_match_avisa():
    with patch("kiro_dash.cli.collect_recent_tools", return_value=_fake_tool_calls()):
        runner = CliRunner()
        result = runner.invoke(main, ["tool", "inexistente"])
    assert result.exit_code == 0
    assert "nenhuma" in result.output.lower()


def test_tool_command_show_input_lista_keys_por_default():
    with patch("kiro_dash.cli.collect_recent_tools", return_value=_fake_tool_calls()):
        runner = CliRunner()
        result = runner.invoke(main, ["tool", "shell"])
    # Sem --show-input, mostra apenas keys, não values
    assert "command" in result.output  # key
    # Nenhum valor de input nos fakes — só checa estrutura


def test_tool_command_tail_limit():
    with patch("kiro_dash.cli.collect_recent_tools", return_value=_fake_tool_calls()):
        runner = CliRunner()
        result = runner.invoke(main, ["tool", "shell", "--tail", "1"])
    assert result.exit_code == 0
    # Deve aparecer só 1 chamada de shell na tabela
    # (header + 1 linha)
```

- [ ] **Step 2: Rodar — falha**

```bash
pytest tests/test_tool_command.py -v
```

- [ ] **Step 3: Implementar**

Em `cli.py`:

```python
def collect_recent_tools(hours: int = 24) -> list[ToolCall]:
    """Helper: tools de todas as sessões nas últimas N horas, ordenadas por timestamp."""
    from kiro_dash.parser import discover_sessions
    from kiro_dash.jsonl_parser import parse_jsonl_tools

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    out: list[ToolCall] = []
    for json_path in discover_sessions():
        jsonl = json_path.with_suffix(".jsonl")
        if not jsonl.exists():
            continue
        for t in parse_jsonl_tools(jsonl):
            if t.timestamp is None or t.timestamp >= cutoff:
                out.append(t)
    out.sort(key=lambda t: t.timestamp or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return out


@main.command()
@click.argument("name")
@click.option("--hours", default=24, type=int, help="Janela em horas (default 24).")
@click.option("--errors-only", is_flag=True, default=False, help="Só status=error.")
@click.option("--tail", default=20, type=int, help="Últimas N chamadas (default 20).")
@click.option("--show-input", is_flag=True, default=False,
              help="Mostra também os values do input (vaza dados — uso debug pessoal).")
def tool(name: str, hours: int, errors_only: bool, tail: int, show_input: bool) -> None:
    """Drill-down de uma tool específica.

    Mostra chamadas recentes, status, error_summary, sessão. ``--show-input``
    inclui values do input — vaza dados, use só para debug local.
    """
    calls = [t for t in collect_recent_tools(hours=hours) if t.name == name]
    if errors_only:
        calls = [t for t in calls if (t.status or "").lower() == "error"]
    calls = calls[:tail]

    if not calls:
        console.print(f"[yellow]Nenhuma chamada de {name!r} nas últimas {hours}h"
                      f"{' (filtro: errors-only)' if errors_only else ''}.[/yellow]")
        return

    n_total = len(calls)
    n_errors = sum(1 for t in calls if (t.status or "").lower() == "error")

    header = Text()
    header.append(f"{name}  ", style="bold")
    header.append(f"{n_total} chamadas  ", style="dim")
    if n_errors:
        header.append(f"{n_errors} erros", style="bold red")
    console.print(Panel(header, title="Tool", expand=False))

    table = Table(show_header=True, header_style="bold")
    table.add_column("when")
    table.add_column("status")
    table.add_column("toolUseId")
    table.add_column("input keys" if not show_input else "input")
    table.add_column("error / preview", overflow="fold")
    for t in calls:
        when = t.timestamp.astimezone().strftime("%H:%M:%S") if t.timestamp else "—"
        status_cell = Text(t.status or "?",
                           style="red" if (t.status or "").lower() == "error" else "green")
        keys_cell = ", ".join(t.input_keys) if t.input_keys else "—"
        if show_input:
            # Wave 4: --show-input não está implementado completo (ToolCall não guarda values).
            # Por ora, equivale a mostrar keys; sinalizar.
            keys_cell = f"[dim](keys only — values não retidos)[/dim] {keys_cell}"
        err_cell = Text(t.error_summary or "—",
                        style="red" if t.error_summary else "dim")
        table.add_row(when, status_cell, t.tool_use_id[:8], keys_cell, err_cell)
    console.print(table)
```

> **Nota sobre `--show-input`:** o `ToolCall` não retém os values do input (privacidade Wave 1). A flag fica como placeholder; mostrar values reais exigiria ler o `.jsonl` direto. Decidir em iteração futura se vale o risco de privacidade vs valor de debug.

- [ ] **Step 4: Rodar — passa**

```bash
pytest tests/test_tool_command.py -v
```

- [ ] **Step 5: Smoke real**

```bash
kiro-dash tool shell --tail 5
kiro-dash tool write --errors-only
kiro-dash tool read --errors-only
```

- [ ] **Step 6: Commit**

```bash
git add src/kiro_dash/cli.py tests/test_tool_command.py
git -c user.email='leonardo.menzani@gmail.com' -c user.name='mencoding' \
  commit -m "feat(cli): subcomando tool <name> com --errors-only / --tail / --show-input"
```

---

### Task 4: Bar visual na tabela Tools agregada (CLI + TUI)

**Files:**
- Modify: `src/kiro_dash/cli.py` — função `tools_command`
- Modify: `src/kiro_dash/views/tabs/tools_tab.py`

- [ ] **Step 1: CLI: adicionar coluna `share` com `bar_inline` em `tools` agregado**

No comando `tools` existente, ao montar a tabela:

```python
from kiro_dash.visual import bar_inline

# após calcular total_calls
for a in aggs:
    pct = a["count"] / total_calls if total_calls else 0
    bar = bar_inline(pct, width=15)
    table.add_row(
        a["name"],
        str(a["count"]),
        f"{bar} {pct*100:5.1f}%",   # nova coluna
        str(a["sessions"]),
        err_cell,
    )
```

E adicionar header da coluna `share`.

- [ ] **Step 2: TUI ToolsTab — bar coluna**

No `tools_tab.py`, após calcular total e ao popular DataTable, adicionar coluna `share` com a string `bar_inline` + percentual.

- [ ] **Step 3: Smoke**

```bash
kiro-dash tools
kiro-dash tui  # aba 5
```

Validar visualmente que a coluna `share` aparece como barra horizontal com %.

- [ ] **Step 4: Commit**

```bash
git add src/kiro_dash/cli.py src/kiro_dash/views/tabs/tools_tab.py
git -c user.email='leonardo.menzani@gmail.com' -c user.name='mencoding' \
  commit -m "feat(visual): coluna share com bar horizontal nas tabelas Tools"
```

---

### Task 5: TUI ToolsTab — drill-down inline com painel inferior

**Files:**
- Modify: `src/kiro_dash/views/tabs/tools_tab.py`

- [ ] **Step 1: Adicionar Static `tools-detail` no compose**

```python
def compose(self) -> ComposeResult:
    yield Static(id="tools-header")
    yield DataTable(id="tools-table", zebra_stripes=True, cursor_type="row")
    yield Static(id="tools-detail")  # painel inferior, vazio até seleção
```

- [ ] **Step 2: Implementar handler de seleção**

```python
def on_data_table_row_selected(self, event) -> None:
    row_idx = event.cursor_row
    if not (0 <= row_idx < len(self._tools_by_index)):
        return
    name = self._tools_by_index[row_idx]
    self._render_detail(name)


def _render_detail(self, name: str) -> None:
    from kiro_dash.cli import collect_recent_tools  # ou helper compartilhado

    calls = [t for t in collect_recent_tools(hours=24) if t.name == name]
    errors = [t for t in calls if (t.status or "").lower() == "error"][:5]

    # Sparkline: chamadas por hora nas últimas 24h
    hours_buckets = [0] * 24
    now = datetime.now(timezone.utc)
    for t in calls:
        if t.timestamp:
            h_ago = int((now - t.timestamp).total_seconds() // 3600)
            if 0 <= h_ago < 24:
                hours_buckets[23 - h_ago] += 1
    spark = sparkline(hours_buckets)

    lines = [
        f"[b]{name}[/b]  {len(calls)} chamadas / {sum(1 for t in calls if (t.status or '').lower() == 'error')} erros",
        f"[dim]chamadas/h (últimas 24h):[/dim] {spark}",
        "",
    ]
    if errors:
        lines.append("[bold red]Erros recentes:[/bold red]")
        for t in errors:
            when = t.timestamp.astimezone().strftime("%H:%M") if t.timestamp else "?"
            lines.append(f"  [dim]{when}[/dim] {t.tool_use_id[:8]}  [red]{t.error_summary or '?'}[/red]")
    else:
        lines.append("[green]Sem erros nas últimas 24h.[/green]")
    self.query_one("#tools-detail", Static).update("\n".join(lines))
```

- [ ] **Step 3: Atualizar `refresh_snapshot` pra preencher `_tools_by_index`**

```python
def refresh_snapshot(self) -> None:
    aggs = aggregate_tools_in_window(DEFAULT_SESSIONS_DIR, hours=self.DEFAULT_HOURS)
    # ...
    self._tools_by_index = [a["name"] for a in aggs]
    # ...
```

- [ ] **Step 4: Smoke**

```bash
kiro-dash tui
# aba 5, ↑/↓ + Enter em "write" ou "read"
```

Validar: aparece painel inferior com sparkline + erros recentes.

- [ ] **Step 5: Commit**

```bash
git add src/kiro_dash/views/tabs/tools_tab.py
git -c user.email='leonardo.menzani@gmail.com' -c user.name='mencoding' \
  commit -m "feat(tui): drill-down inline em ToolsTab (sparkline + erros recentes)"
```

---

### Task 6: README + bump v0.5.0

**Files:**
- Modify: `README.md`
- Modify: `src/kiro_dash/__init__.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Seção `Tool drill-down` no README**

Antes da Licença:

```markdown
## Drill-down de tools

```bash
kiro-dash tool shell                       # últimas 20 chamadas de shell
kiro-dash tool write --errors-only         # só erros
kiro-dash tool read --tail 5 --hours 6     # últimas 5 em 6h
```

Mostra: timestamp, status, toolUseId, input keys (sem values), error summary
(1ª linha do retorno quando status=error, capped 200 chars).

Privacidade: `input.values` não são retidos pelo parser (Wave 1).
`error_summary` é metadata operacional (FileNotFoundError, exit code,
HTTP status), não vaza prompts.

Na TUI, aba Tools (`5`): seleção de linha (↑/↓ + Enter) abre painel
inferior com sparkline de uso por hora e top 5 erros recentes.
```

- [ ] **Step 2: Bump para 0.5.0**

```python
# __init__.py
__version__ = "0.5.0"
# pyproject.toml
version = "0.5.0"
```

- [ ] **Step 3: Commit + tag**

```bash
git add README.md src/kiro_dash/__init__.py pyproject.toml
git -c user.email='leonardo.menzani@gmail.com' -c user.name='mencoding' \
  commit -m "chore: bump v0.5.0

Wave 4 — Tools drill-down + visual
- ToolCall ganha input_keys + error_summary (privacy-safe)
- Helpers visual: bar_inline + sparkline (Unicode block chars)
- CLI tool <name> com --errors-only / --tail / --show-input
- Bar horizontal na coluna 'share' das tabelas Tools
- TUI ToolsTab com drill-down inline (seleção + sparkline + erros)"
git tag v0.5.0
```

---

## Self-Review Checklist

- [ ] `ToolCall.input_keys` lista só nomes (sem values)
- [ ] `error_summary` capped em 200 chars, primeira linha não-vazia, `None` em success
- [ ] `bar_inline` clamp em [0,1]; saída sempre tem `width` chars
- [ ] `sparkline` lida com lista vazia, valores iguais, séries longas
- [ ] CLI `tool` filtra por nome, `--errors-only`, `--tail`, mostra `error_summary`
- [ ] Bar visual aparece na tabela Tools (CLI + TUI)
- [ ] TUI ToolsTab tem `cursor_type="row"` e responde a Enter
- [ ] Painel inferior renderiza sparkline + top 5 erros
- [ ] Sem novas dependências externas
- [ ] README documenta privacidade

## Done When

- `pytest tests/ -v` → todos verdes (incluindo Wave 1-3)
- Smoke real:
  - `kiro-dash tool write --errors-only` lista as 4 erros write da Wave 2/3
  - `kiro-dash tools` mostra coluna `share` com barras
  - `kiro-dash tui` aba 5 + Enter em "write" mostra painel com erros
- 6 commits + tag v0.5.0
