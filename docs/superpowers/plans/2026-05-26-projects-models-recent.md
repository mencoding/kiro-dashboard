# Wave 1 / Frente A — `projects` + `models` + `recent` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar 3 subcomandos standalone à CLI (`projects`, `models`, `recent`), reusando o `aggregator` existente, expostos com janela temporal configurável.

**Architecture:** Comandos thin sobre `aggregator.py`. Adicionam apenas: (1) uma função utilitária para janela em N dias (não só hoje) no `aggregator`, (2) três comandos Click no `cli.py` reutilizando os helpers de formatação existentes, (3) testes pytest cobrindo o filtro temporal e os smoke do CLI via `click.testing.CliRunner`.

**Tech Stack:** Python 3.12, Click, Rich, pytest. Sem novas dependências.

**Branch:** `feat/wave1-projects-models-recent`

---

## File Structure

| Arquivo | Responsabilidade | Mudança |
|---|---|---|
| `src/kiro_dash/aggregator.py` | Funções de agregação puras | **Modificar** — adicionar `turns_in_last_days(sessions, days)` |
| `src/kiro_dash/cli.py` | Subcomandos Click + render | **Modificar** — adicionar 3 commands ao final, reusar `_aggregates_table`/`_fmt_credits`/`_fmt_duration`/`_fmt_relative_time` |
| `tests/fixtures/sessions_synthetic.py` | Fábrica de Session/Turn para testes | **Criar** — helper `make_session()` e `make_turn()` para construir objetos sem ler disco |
| `tests/test_aggregator.py` | Testes da função nova | **Criar** |
| `tests/test_cli_projects_models_recent.py` | Testes smoke dos 3 comandos | **Criar** |

---

### Task 1: Helper de fixtures sintéticas

**Files:**
- Create: `tests/fixtures/__init__.py` (vazio)
- Create: `tests/fixtures/sessions_synthetic.py`

- [ ] **Step 1: Criar pacote de fixtures**

```bash
touch /home/menzani/Desenvolvimento/mencoding/kiro-dash/tests/fixtures/__init__.py
```

- [ ] **Step 2: Escrever helper de fixtures**

Criar `tests/fixtures/sessions_synthetic.py` com:

```python
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
```

- [ ] **Step 3: Commit**

```bash
cd /home/menzani/Desenvolvimento/mencoding/kiro-dash
git add tests/fixtures/__init__.py tests/fixtures/sessions_synthetic.py
git commit -m "test(fixtures): adicionar fábricas de Session/Turn sintéticas"
```

---

### Task 2: `turns_in_last_days` — função pura no aggregator

**Files:**
- Modify: `src/kiro_dash/aggregator.py` — adicionar nova função após `turns_in_local_day`
- Create: `tests/test_aggregator.py`

- [ ] **Step 1: Escrever o teste falhando**

Criar `tests/test_aggregator.py`:

```python
"""Testes do agregador — funções de janela temporal."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from kiro_dash.aggregator import turns_in_last_days
from tests.fixtures.sessions_synthetic import make_session, make_turn


def test_turns_in_last_days_filters_by_window():
    now = datetime.now(timezone.utc)
    s = make_session(
        turns=[
            make_turn(end_timestamp=now - timedelta(days=10), credits=1.0),
            make_turn(end_timestamp=now - timedelta(days=3), credits=2.0),
            make_turn(end_timestamp=now - timedelta(hours=1), credits=4.0),
        ]
    )

    pairs = turns_in_last_days([s], days=7)
    credits = sorted(t.credits for _, t in pairs)
    assert credits == [2.0, 4.0]


def test_turns_in_last_days_empty_when_no_match():
    now = datetime.now(timezone.utc)
    s = make_session(turns=[make_turn(end_timestamp=now - timedelta(days=30))])
    assert turns_in_last_days([s], days=7) == []


def test_turns_in_last_days_zero_days_returns_empty():
    now = datetime.now(timezone.utc)
    s = make_session(turns=[make_turn(end_timestamp=now)])
    assert turns_in_last_days([s], days=0) == []
```

- [ ] **Step 2: Rodar teste — falha esperada**

```bash
cd /home/menzani/Desenvolvimento/mencoding/kiro-dash
source .venv/bin/activate
pytest tests/test_aggregator.py -v
```

Expected: 3 FAILED com `ImportError: cannot import name 'turns_in_last_days'`.

- [ ] **Step 3: Implementar a função**

Adicionar em `src/kiro_dash/aggregator.py`, logo após a função `turns_in_local_day` (procure por `def turns_in_local_day` e insira a nova função imediatamente abaixo do final dela, antes do `def _aggregate_pairs`):

```python
def turns_in_last_days(
    sessions: list[Session],
    days: int,
) -> list[tuple[Session, Turn]]:
    """Retorna pares (sessão, turn) cujo end_timestamp caiu nos últimos N dias.

    A janela é aberta no fim (inclui o instante atual) e fechada no início
    em ``now - days``. ``days=0`` devolve lista vazia.
    """
    if days <= 0:
        return []
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    out: list[tuple[Session, Turn]] = []
    for s in sessions:
        for t in s.turns:
            if cutoff <= t.end_timestamp <= now:
                out.append((s, t))
    return out
```

- [ ] **Step 4: Rodar testes — passa**

```bash
pytest tests/test_aggregator.py -v
```

Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/kiro_dash/aggregator.py tests/test_aggregator.py
git commit -m "feat(aggregator): turns_in_last_days para janela de N dias"
```

---

### Task 3: Subcomando `projects`

**Files:**
- Modify: `src/kiro_dash/cli.py` — adicionar comando `projects` ao final, antes do `if __name__ == "__main__"`
- Create: `tests/test_cli_projects_models_recent.py`

- [ ] **Step 1: Escrever teste smoke do comando**

Criar `tests/test_cli_projects_models_recent.py`:

```python
"""Smoke tests dos comandos projects / models / recent via CliRunner."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from click.testing import CliRunner

from kiro_dash.cli import main
from tests.fixtures.sessions_synthetic import make_session, make_turn


def _fake_sessions():
    now = datetime.now(timezone.utc)
    return [
        make_session(
            session_id="aaaa",
            cwd="/proj/alfa",
            model_id="claude-opus-4.7",
            turns=[make_turn(end_timestamp=now - timedelta(hours=1), credits=5.0)],
            is_active=True,
        ),
        make_session(
            session_id="bbbb",
            cwd="/proj/beta",
            model_id="auto",
            turns=[make_turn(end_timestamp=now - timedelta(hours=2), credits=2.0)],
            is_active=False,
            updated_at=now - timedelta(hours=2),
        ),
        make_session(
            session_id="cccc",
            cwd="/proj/alfa",
            model_id="claude-opus-4.7",
            turns=[make_turn(end_timestamp=now - timedelta(days=15), credits=3.0)],
            is_active=False,
            updated_at=now - timedelta(days=15),
        ),
    ]


def test_projects_default_window_aggregates_by_cwd():
    with patch("kiro_dash.cli.load_all_sessions", return_value=_fake_sessions()):
        runner = CliRunner()
        result = runner.invoke(main, ["projects"])
    assert result.exit_code == 0
    # /proj/alfa tem 1 turn na janela default (7d), /proj/beta tem 1
    assert "/proj/alfa" in result.output
    assert "/proj/beta" in result.output
    # Sessão de 15 dias não entra
    assert "3.00" not in result.output or "5.00" in result.output


def test_projects_window_30d_includes_old_session():
    with patch("kiro_dash.cli.load_all_sessions", return_value=_fake_sessions()):
        runner = CliRunner()
        result = runner.invoke(main, ["projects", "--days", "30"])
    assert result.exit_code == 0
    assert "/proj/alfa" in result.output
    # Total de alfa em 30d = 5+3 = 8
    assert "8.00" in result.output
```

- [ ] **Step 2: Rodar — falha esperada (comando não existe)**

```bash
pytest tests/test_cli_projects_models_recent.py::test_projects_default_window_aggregates_by_cwd -v
```

Expected: FAIL com `Error: No such command 'projects'`.

- [ ] **Step 3: Implementar comando**

Em `src/kiro_dash/cli.py`, adicionar import (se ainda não estiver):

```python
from kiro_dash.aggregator import (
    Aggregate,
    active_sessions,
    aggregate_by_agent,
    aggregate_by_cwd,
    aggregate_by_model,
    aggregate_by_session,
    total_credits,
    turns_in_last_days,
    turns_in_local_day,
)
```

E adicionar o comando antes do `if __name__ == "__main__"`:

```python
@main.command()
@click.option("--days", default=7, type=int, help="Janela em dias (default 7).")
@click.option("--limit", default=10, type=int, help="Top N projetos (default 10).")
def projects(days: int, limit: int) -> None:
    """Top projetos (cwd) por créditos consumidos numa janela de N dias."""
    sessions = load_all_sessions()
    pairs = turns_in_last_days(sessions, days=days)
    if not pairs:
        console.print(f"[yellow]Sem turns nos últimos {days} dias.[/yellow]")
        return

    aggs = aggregate_by_cwd(pairs)[:limit]
    total = total_credits(pairs)

    header = Text()
    header.append(f"últimos {days}d  ", style="bold")
    header.append(f"{_fmt_credits(total)} créditos", style="bold green")
    console.print(Panel(header, title="Projetos", expand=False))
    console.print(_aggregates_table("Por projeto (cwd)", aggs, "cwd"))
```

- [ ] **Step 4: Rodar — passa**

```bash
pytest tests/test_cli_projects_models_recent.py::test_projects_default_window_aggregates_by_cwd \
       tests/test_cli_projects_models_recent.py::test_projects_window_30d_includes_old_session -v
```

Expected: 2 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/kiro_dash/cli.py tests/test_cli_projects_models_recent.py
git commit -m "feat(cli): subcomando projects com janela --days e --limit"
```

---

### Task 4: Subcomando `models`

**Files:**
- Modify: `src/kiro_dash/cli.py`
- Modify: `tests/test_cli_projects_models_recent.py`

- [ ] **Step 1: Adicionar teste**

Acrescentar em `tests/test_cli_projects_models_recent.py`:

```python
def test_models_default_window_aggregates_by_model_id():
    with patch("kiro_dash.cli.load_all_sessions", return_value=_fake_sessions()):
        runner = CliRunner()
        result = runner.invoke(main, ["models"])
    assert result.exit_code == 0
    assert "claude-opus-4.7" in result.output
    assert "auto" in result.output
```

- [ ] **Step 2: Rodar — falha**

```bash
pytest tests/test_cli_projects_models_recent.py::test_models_default_window_aggregates_by_model_id -v
```

Expected: FAIL com `Error: No such command 'models'`.

- [ ] **Step 3: Implementar comando**

Adicionar em `src/kiro_dash/cli.py` logo após `projects`:

```python
@main.command()
@click.option("--days", default=7, type=int, help="Janela em dias (default 7).")
@click.option("--limit", default=10, type=int, help="Top N modelos (default 10).")
def models(days: int, limit: int) -> None:
    """Top modelos por créditos consumidos numa janela de N dias."""
    sessions = load_all_sessions()
    pairs = turns_in_last_days(sessions, days=days)
    if not pairs:
        console.print(f"[yellow]Sem turns nos últimos {days} dias.[/yellow]")
        return

    aggs = aggregate_by_model(pairs)[:limit]
    total = total_credits(pairs)

    header = Text()
    header.append(f"últimos {days}d  ", style="bold")
    header.append(f"{_fmt_credits(total)} créditos", style="bold green")
    console.print(Panel(header, title="Modelos", expand=False))
    console.print(_aggregates_table("Por modelo", aggs, "modelo"))
```

- [ ] **Step 4: Rodar — passa**

```bash
pytest tests/test_cli_projects_models_recent.py::test_models_default_window_aggregates_by_model_id -v
```

Expected: PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/kiro_dash/cli.py tests/test_cli_projects_models_recent.py
git commit -m "feat(cli): subcomando models com janela --days e --limit"
```

---

### Task 5: Subcomando `recent`

**Files:**
- Modify: `src/kiro_dash/cli.py`
- Modify: `tests/test_cli_projects_models_recent.py`

- [ ] **Step 1: Adicionar teste**

```python
def test_recent_orders_by_updated_at_desc():
    with patch("kiro_dash.cli.load_all_sessions", return_value=_fake_sessions()):
        runner = CliRunner()
        result = runner.invoke(main, ["recent", "--limit", "5"])
    assert result.exit_code == 0
    # aaaa é a mais recente (updated_at = now), bbbb depois (-2h), cccc por último (-15d)
    pos_a = result.output.find("aaaa")
    pos_b = result.output.find("bbbb")
    pos_c = result.output.find("cccc")
    assert 0 <= pos_a < pos_b < pos_c


def test_recent_marks_active_sessions():
    with patch("kiro_dash.cli.load_all_sessions", return_value=_fake_sessions()):
        runner = CliRunner()
        result = runner.invoke(main, ["recent"])
    assert result.exit_code == 0
    # Pelo menos um marcador visual para 'aaaa' (que tem is_active=True)
    # — usamos '●' como marcador (igual ao `session`)
    assert "●" in result.output
```

- [ ] **Step 2: Rodar — falha**

```bash
pytest tests/test_cli_projects_models_recent.py::test_recent_orders_by_updated_at_desc -v
```

Expected: FAIL com `Error: No such command 'recent'`.

- [ ] **Step 3: Implementar comando**

Adicionar em `src/kiro_dash/cli.py` logo após `models`:

```python
@main.command()
@click.option("--limit", default=20, type=int, help="N últimas sessões (default 20).")
def recent(limit: int) -> None:
    """Últimas N sessões ordenadas por updated_at desc, ativas marcadas com ●."""
    sessions = load_all_sessions()
    if not sessions:
        console.print("[yellow]Nenhuma sessão encontrada.[/yellow]")
        return

    sessions = sorted(sessions, key=lambda s: s.updated_at, reverse=True)[:limit]

    table = Table(title=f"Últimas {len(sessions)} sessões", expand=False, header_style="bold")
    table.add_column("sid")
    table.add_column("título", overflow="fold")
    table.add_column("agent")
    table.add_column("modelo")
    table.add_column("turns", justify="right")
    table.add_column("créditos", justify="right")
    table.add_column("atualizada")

    for s in sessions:
        sid = f"{s.session_id[:8]}{' ●' if s.is_active else ''}"
        title = (s.title or "—")[:60]
        table.add_row(
            sid,
            title,
            s.agent_name or "?",
            s.model_id,
            str(len(s.turns)),
            _fmt_credits(s.total_credits),
            _fmt_relative_time(s.updated_at),
        )

    console.print(table)
```

- [ ] **Step 4: Rodar — passa**

```bash
pytest tests/test_cli_projects_models_recent.py -v
```

Expected: 5 PASSED total.

- [ ] **Step 5: Smoke manual com dados reais**

```bash
kiro-dash projects
kiro-dash models
kiro-dash recent --limit 5
kiro-dash projects --days 30
```

Expected: cada um exibe panel + table sem erro, totais batem com `kiro-dash today`.

- [ ] **Step 6: Commit**

```bash
git add src/kiro_dash/cli.py tests/test_cli_projects_models_recent.py
git commit -m "feat(cli): subcomando recent com flag --limit e marcador de ativa"
```

---

## Self-Review Checklist

- [ ] Cobertura: 3 comandos novos + 1 função `turns_in_last_days` + 5 testes
- [ ] Sem placeholders ("TBD", "implementar depois", etc)
- [ ] Tipos consistentes — `turns_in_last_days(sessions, days=...)` com mesma signature em test e impl
- [ ] Imports atualizados no `cli.py` para incluir `turns_in_last_days`
- [ ] Todos os comandos usam `_aggregates_table` / `_fmt_*` existentes (DRY)
- [ ] Mensagens de erro/empty consistentes em pt-BR

## Done When

- `pytest tests/test_aggregator.py tests/test_cli_projects_models_recent.py -v` → todos passam
- `kiro-dash projects` / `models` / `recent` rodam sem erro contra dados reais
- 5 commits no branch `feat/wave1-projects-models-recent`
