# Wave 2 / Frente G — Filtros temporais + heurística de projeto Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar (1) função `project_label(cwd)` com heurística que mapeia paths para labels conceituais (`institucional/auto-normas`, `mencoding/kiro-dash`, `nyx`); (2) janelas temporais nomeadas (`--week`, `--month`, `--cycle`, `--all`) em `today`/`projects`/`models`; (3) novo `aggregate_by_project` que reusa a heurística mantendo `aggregate_by_cwd` como compatibilidade.

**Architecture:**

- Novo módulo `kiro_dash.project` com regras hardcoded conforme estrutura real do Léo (`~/iris/projetos/<categoria>/...`, `~/Desenvolvimento/<conta>/<repo>/...`, `~/nyx`, fallback literal).
- `aggregator` ganha `aggregate_by_project` que aplica `project_label` antes de agrupar.
- CLI adiciona flag `--window` (mutuamente exclusiva com `--days`) que aceita `today|week|month|cycle|all|<int>`.
- Override por TOML fica para Wave 3 (aliás vem **depois** das fundações desta wave).

**Tech Stack:** Python 3.12 padrão, sem novas dependências.

**Branch:** `feat/wave2-projects-windows`

---

## File Structure

| Arquivo | Responsabilidade | Mudança |
|---|---|---|
| `src/kiro_dash/project.py` | `project_label(cwd)` heurístico | **Criar** |
| `src/kiro_dash/aggregator.py` | `aggregate_by_project` + helper de janela `resolve_window` | **Modificar** |
| `src/kiro_dash/cli.py` | Flags `--window` em `today/projects/models`; usar `aggregate_by_project` | **Modificar** |
| `tests/test_project.py` | Cobertura das regras | **Criar** |
| `tests/test_window_resolver.py` | Cobertura de janelas nomeadas | **Criar** |

---

### Task 1: Heurística `project_label` com regras hardcoded

**Files:**
- Create: `src/kiro_dash/project.py`
- Create: `tests/test_project.py`

- [ ] **Step 1: Escrever testes (todas as regras)**

Criar `tests/test_project.py`:

```python
"""Cobertura da heurística project_label."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from kiro_dash.project import project_label


@pytest.fixture
def home(tmp_path: Path):
    """Substitui Path.home() por tmp_path durante o teste."""
    with patch.object(Path, "home", return_value=tmp_path):
        yield tmp_path


def test_iris_projetos_categoria_projeto(home):
    cwd = str(home / "iris/projetos/institucional/auto-normas")
    assert project_label(cwd) == "institucional/auto-normas"


def test_iris_projetos_categoria_projeto_subpasta(home):
    cwd = str(home / "iris/projetos/institucional/auto-normas/workspace")
    assert project_label(cwd) == "institucional/auto-normas"


def test_iris_projetos_categoria_geral_sub(home):
    cwd = str(home / "iris/projetos/institucional/geral")
    assert project_label(cwd) == "institucional/geral"


def test_iris_projetos_pessoal(home):
    cwd = str(home / "iris/projetos/pessoal/docente-ifsp")
    assert project_label(cwd) == "pessoal/docente-ifsp"


def test_iris_projetos_concluidos(home):
    cwd = str(home / "iris/projetos/concluidos/normas-centralizadas")
    assert project_label(cwd) == "concluidos/normas-centralizadas"


def test_iris_normativos(home):
    cwd = str(home / "iris/projetos/normativos")
    assert project_label(cwd) == "iris-normativos"


def test_iris_normativos_subdir(home):
    cwd = str(home / "iris/projetos/normativos/ifsp")
    assert project_label(cwd) == "iris-normativos"


def test_iris_referencias(home):
    cwd = str(home / "iris/projetos/referencias/info-pessoal")
    assert project_label(cwd) == "iris-referencias"


def test_iris_projetos_sem_categoria_reconhecida(home):
    cwd = str(home / "iris/projetos")
    assert project_label(cwd) == "iris-projetos"


def test_iris_geral_root(home):
    cwd = str(home / "iris")
    assert project_label(cwd) == "iris-geral"


def test_iris_geral_outras_pastas(home):
    cwd = str(home / "iris/audit")
    assert project_label(cwd) == "iris-geral"


def test_dev_pessoal_padrao(home):
    cwd = str(home / "Desenvolvimento/mencoding/kiro-dash")
    assert project_label(cwd) == "mencoding/kiro-dash"


def test_dev_pessoal_subdir(home):
    cwd = str(home / "Desenvolvimento/mencoding/kiro-dash/.worktrees/x")
    assert project_label(cwd) == "mencoding/kiro-dash"


def test_dev_ifsp_3_niveis(home):
    cwd = str(home / "Desenvolvimento/ifsp/incubadora/projeto-x")
    assert project_label(cwd) == "ifsp/incubadora/projeto-x"


def test_nyx(home):
    cwd = str(home / "nyx")
    assert project_label(cwd) == "nyx"


def test_nyx_subdir(home):
    cwd = str(home / "nyx/memory")
    assert project_label(cwd) == "nyx"


def test_path_fora_de_padrao_devolve_relativo_ao_home(home):
    cwd = str(home / "outras-coisas/path-x")
    assert project_label(cwd) == "outras-coisas/path-x"


def test_path_completamente_fora_do_home_devolve_literal():
    assert project_label("/tmp/coisa") == "/tmp/coisa"


def test_cwd_vazio_retorna_interrogacao():
    assert project_label("") == "?"


def test_cwd_none_safe():
    assert project_label(None) == "?"  # type: ignore[arg-type]
```

- [ ] **Step 2: Rodar — falha esperada**

```bash
cd /home/menzani/Desenvolvimento/mencoding/kiro-dash
source .venv/bin/activate
pytest tests/test_project.py -v
```

Expected: 19 falhas (`ImportError`).

- [ ] **Step 3: Implementar `project.py`**

Criar `src/kiro_dash/project.py`:

```python
"""Heurística de mapeamento ``cwd → label de projeto``.

Reflete a estrutura real do workspace do Léo:

- ``~/iris/projetos/<categoria>/<projeto>/...`` → ``<categoria>/<projeto>``
  Categorias reconhecidas: ``pessoal``, ``profissional``, ``institucional``,
  ``concluidos``.
- ``~/iris/projetos/normativos/...`` → ``iris-normativos``
- ``~/iris/projetos/referencias/...`` → ``iris-referencias``
- ``~/iris/projetos/...`` (sem categoria reconhecida) → ``iris-projetos``
- ``~/iris/...`` (outros subdirs) → ``iris-geral``
- ``~/Desenvolvimento/ifsp/<grupo>/<repo>/...`` → ``ifsp/<grupo>/<repo>``
- ``~/Desenvolvimento/<conta>/<repo>/...`` → ``<conta>/<repo>``
- ``~/nyx/...`` → ``nyx``
- Outros paths sob o HOME → caminho relativo ao HOME (sem prefix)
- Paths absolutos fora do HOME → literal
- ``cwd`` vazio/None → ``"?"``

Override declarativo via TOML fica como issue Wave 3.
"""
from __future__ import annotations

import re
from pathlib import Path

_KNOWN_CATEGORIES = {"pessoal", "profissional", "institucional", "concluidos"}


def _home_root() -> str:
    return str(Path.home())


def project_label(cwd: str | None) -> str:
    """Mapeia ``cwd`` para um label conceitual de projeto.

    Aplica regras na ordem; primeira que casa, vence.
    """
    if not cwd:
        return "?"

    home = _home_root()

    # Regra 1: iris/projetos/<categoria>/<projeto>(/...)?
    m = re.match(
        rf"^{re.escape(home)}/iris/projetos/([^/]+)/([^/]+)(?:/.*)?$",
        cwd,
    )
    if m:
        cat, proj = m.group(1), m.group(2)
        if cat in _KNOWN_CATEGORIES:
            return f"{cat}/{proj}"

    # Regra 2: iris/projetos/normativos
    if cwd.startswith(f"{home}/iris/projetos/normativos"):
        return "iris-normativos"

    # Regra 3: iris/projetos/referencias
    if cwd.startswith(f"{home}/iris/projetos/referencias"):
        return "iris-referencias"

    # Regra 4: iris/projetos/* sem categoria reconhecida (ou raiz)
    if (
        cwd == f"{home}/iris/projetos"
        or cwd.startswith(f"{home}/iris/projetos/")
    ):
        return "iris-projetos"

    # Regra 5: iris/... (root ou outros subdirs)
    if cwd == f"{home}/iris" or cwd.startswith(f"{home}/iris/"):
        return "iris-geral"

    # Regra 6: Desenvolvimento/ifsp/<grupo>/<repo>(/...)?
    m = re.match(
        rf"^{re.escape(home)}/Desenvolvimento/ifsp/([^/]+)/([^/]+)(?:/.*)?$",
        cwd,
    )
    if m:
        return f"ifsp/{m.group(1)}/{m.group(2)}"

    # Regra 7: Desenvolvimento/<conta>/<repo>(/...)?
    m = re.match(
        rf"^{re.escape(home)}/Desenvolvimento/([^/]+)/([^/]+)(?:/.*)?$",
        cwd,
    )
    if m:
        return f"{m.group(1)}/{m.group(2)}"

    # Regra 8: nyx
    if cwd == f"{home}/nyx" or cwd.startswith(f"{home}/nyx/"):
        return "nyx"

    # Regra 9: outros paths sob HOME → caminho relativo
    if cwd.startswith(f"{home}/"):
        return cwd[len(home) + 1:]

    # Regra 10: literal
    return cwd
```

- [ ] **Step 4: Rodar — passa**

```bash
pytest tests/test_project.py -v
```

Expected: 19 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/kiro_dash/project.py tests/test_project.py
git commit -m "feat(project): heurística project_label com 9 regras + 19 testes"
```

---

### Task 2: `aggregate_by_project` + `resolve_window`

**Files:**
- Modify: `src/kiro_dash/aggregator.py`
- Modify: `tests/test_aggregator.py`
- Create: `tests/test_window_resolver.py`

- [ ] **Step 1: Escrever teste de `aggregate_by_project`**

Em `tests/test_aggregator.py`, acrescentar:

```python
import os
from unittest.mock import patch
from pathlib import Path

from kiro_dash.aggregator import aggregate_by_project


def test_aggregate_by_project_consolida_subpastas_em_um_label(tmp_path):
    """Sessões em subpastas do mesmo projeto consolidam num único label."""
    with patch.object(Path, "home", return_value=tmp_path):
        s1 = make_session(
            session_id="aaaa",
            cwd=str(tmp_path / "iris/projetos/institucional/auto-normas"),
            turns=[make_turn(end_timestamp=datetime.now(timezone.utc), credits=1.0)],
        )
        s2 = make_session(
            session_id="bbbb",
            cwd=str(tmp_path / "iris/projetos/institucional/auto-normas/workspace"),
            turns=[make_turn(end_timestamp=datetime.now(timezone.utc), credits=2.0)],
        )
        s3 = make_session(
            session_id="cccc",
            cwd=str(tmp_path / "iris/projetos/pessoal/docente-ifsp"),
            turns=[make_turn(end_timestamp=datetime.now(timezone.utc), credits=4.0)],
        )

        pairs = [
            (s, t)
            for s in (s1, s2, s3)
            for t in s.turns
        ]

        aggs = aggregate_by_project(pairs)

    by_label = {a.label: a for a in aggs}
    assert "institucional/auto-normas" in by_label
    assert by_label["institucional/auto-normas"].credits == 3.0
    assert by_label["institucional/auto-normas"].sessions == 2
    assert by_label["pessoal/docente-ifsp"].credits == 4.0
```

- [ ] **Step 2: Escrever teste de `resolve_window`**

Criar `tests/test_window_resolver.py`:

```python
"""Cobertura do resolver de janela nomeada (--window)."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from kiro_dash.aggregator import resolve_window
from tests.fixtures.sessions_synthetic import make_session, make_turn


def _turn(when: datetime, credits: float = 1.0):
    return make_turn(end_timestamp=when, credits=credits)


def test_resolve_window_today():
    now = datetime.now().astimezone()
    today = make_session(turns=[_turn(now.astimezone(timezone.utc))])
    yesterday = make_session(
        session_id="y",
        turns=[_turn((now - timedelta(days=1)).astimezone(timezone.utc))],
    )
    pairs = resolve_window([today, yesterday], "today", cycle_start=date.today().replace(day=1))
    assert len(pairs) == 1


def test_resolve_window_week():
    now = datetime.now(timezone.utc)
    s = make_session(turns=[
        _turn(now - timedelta(days=2)),
        _turn(now - timedelta(days=10)),
    ])
    pairs = resolve_window([s], "week", cycle_start=date(2000, 1, 1))
    assert len(pairs) == 1


def test_resolve_window_month():
    now = datetime.now(timezone.utc)
    s = make_session(turns=[
        _turn(now - timedelta(days=15)),
        _turn(now - timedelta(days=45)),
    ])
    pairs = resolve_window([s], "month", cycle_start=date(2000, 1, 1))
    assert len(pairs) == 1


def test_resolve_window_cycle():
    cycle_start = date.today().replace(day=1)
    now = datetime.now(timezone.utc)
    s = make_session(turns=[
        _turn(now),
        _turn(now - timedelta(days=400)),
    ])
    pairs = resolve_window([s], "cycle", cycle_start=cycle_start)
    assert len(pairs) == 1


def test_resolve_window_all():
    now = datetime.now(timezone.utc)
    s = make_session(turns=[
        _turn(now - timedelta(days=400)),
        _turn(now),
    ])
    pairs = resolve_window([s], "all", cycle_start=date(2000, 1, 1))
    assert len(pairs) == 2


def test_resolve_window_int_string_dias():
    now = datetime.now(timezone.utc)
    s = make_session(turns=[_turn(now - timedelta(days=3))])
    pairs = resolve_window([s], "5", cycle_start=date(2000, 1, 1))
    assert len(pairs) == 1
    pairs = resolve_window([s], "2", cycle_start=date(2000, 1, 1))
    assert len(pairs) == 0


def test_resolve_window_invalid_raises():
    with pytest.raises(ValueError):
        resolve_window([], "ontem", cycle_start=date(2000, 1, 1))
```

- [ ] **Step 3: Rodar — falhas esperadas**

```bash
pytest tests/test_aggregator.py tests/test_window_resolver.py -v
```

Expected: novos testes falham (ImportError).

- [ ] **Step 4: Implementar em `aggregator.py`**

Adicionar imports e funções:

```python
from kiro_dash.project import project_label

# (...)

def aggregate_by_project(pairs: list[tuple[Session, Turn]]) -> list[Aggregate]:
    """Agrega por ``project_label(s.cwd)`` (heurística — Frente G).

    Consolida sub-cwds do mesmo projeto sob um único label.
    """
    return _aggregate_pairs(pairs, key=lambda s, t: project_label(s.cwd))


def resolve_window(
    sessions: list[Session],
    window: str,
    *,
    cycle_start: date,
) -> list[tuple[Session, Turn]]:
    """Resolve uma janela nomeada para pares (sessão, turn).

    ``window`` aceita: ``today``, ``week``, ``month``, ``cycle``, ``all``,
    ou string com inteiro (interpretado como dias). Levanta ``ValueError``
    pra valores não reconhecidos.
    """
    w = window.strip().lower()
    if w == "today":
        return turns_in_local_day(sessions)
    if w == "week":
        return turns_in_last_days(sessions, days=7)
    if w == "month":
        return turns_in_last_days(sessions, days=30)
    if w == "cycle":
        return turns_in_cycle(sessions, cycle_start)
    if w == "all":
        return [(s, t) for s in sessions for t in s.turns]

    # Int → days
    try:
        n = int(w)
    except ValueError as exc:
        raise ValueError(
            f"window inválido: '{window}'. Use today/week/month/cycle/all ou um inteiro de dias."
        ) from exc
    if n < 0:
        raise ValueError(f"window negativo: {n}")
    return turns_in_last_days(sessions, days=n)
```

- [ ] **Step 5: Rodar — passa**

```bash
pytest tests/test_aggregator.py tests/test_window_resolver.py -v
```

Expected: todos passam.

- [ ] **Step 6: Commit**

```bash
git add src/kiro_dash/aggregator.py tests/test_aggregator.py tests/test_window_resolver.py
git commit -m "feat(aggregator): aggregate_by_project + resolve_window nomeadas"
```

---

### Task 3: Plugar `--window` em `today`/`projects`/`models` + usar projeto heurístico

**Files:**
- Modify: `src/kiro_dash/cli.py`
- Modify: `tests/test_cli_projects_models_recent.py`

- [ ] **Step 1: Adicionar testes de janela**

Acrescentar em `tests/test_cli_projects_models_recent.py`:

```python
def test_projects_window_all_inclui_tudo():
    with patch("kiro_dash.cli.load_all_sessions", return_value=_fake_sessions()):
        runner = CliRunner()
        result = runner.invoke(main, ["projects", "--window", "all"])
    assert result.exit_code == 0
    # Sessão de 15d entra com window=all
    assert "8.00" in result.output


def test_projects_window_invalid_returns_error():
    with patch("kiro_dash.cli.load_all_sessions", return_value=_fake_sessions()):
        runner = CliRunner()
        result = runner.invoke(main, ["projects", "--window", "ontem"])
    assert result.exit_code != 0
    assert "window" in result.output.lower()
```

- [ ] **Step 2: Rodar — falha**

```bash
pytest tests/test_cli_projects_models_recent.py -v -k "window_all or window_invalid"
```

Expected: FAIL (flag não existe).

- [ ] **Step 3: Modificar comandos `projects` e `models` no `cli.py`**

Substituir as definições atuais por versões com `--window`:

```python
@main.command()
@click.option(
    "--window",
    default="week",
    help="Janela: today | week | month | cycle | all | <int dias> (default 'week').",
)
@click.option("--days", default=None, type=int, help="(legacy) override em dias.")
@click.option("--limit", default=10, type=int, help="Top N (default 10).")
def projects(window: str, days: int | None, limit: int) -> None:
    """Top projetos (heurística) por créditos numa janela nomeada ou em N dias."""
    sessions = load_all_sessions()
    plan_cfg = load_plan(default_config_path())
    try:
        if days is not None:
            pairs = turns_in_last_days(sessions, days=days)
            window_label = f"últimos {days}d"
        else:
            pairs = resolve_window(sessions, window, cycle_start=plan_cfg.cycle_start)
            window_label = f"janela={window}"
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(2)

    if not pairs:
        console.print(f"[yellow]Sem turns na janela ({window_label}).[/yellow]")
        return

    aggs = aggregate_by_project(pairs)[:limit]
    total = total_credits(pairs)

    header = Text()
    header.append(f"{window_label}  ", style="bold")
    header.append(f"{_fmt_credits(total)} créditos", style="bold green")
    console.print(Panel(header, title="Projetos", expand=False))
    console.print(_aggregates_table("Por projeto", aggs, "projeto"))


@main.command()
@click.option("--window", default="week",
              help="Janela: today | week | month | cycle | all | <int dias> (default 'week').")
@click.option("--days", default=None, type=int, help="(legacy) override em dias.")
@click.option("--limit", default=10, type=int, help="Top N (default 10).")
def models(window: str, days: int | None, limit: int) -> None:
    """Top modelos por créditos numa janela nomeada ou em N dias."""
    sessions = load_all_sessions()
    plan_cfg = load_plan(default_config_path())
    try:
        if days is not None:
            pairs = turns_in_last_days(sessions, days=days)
            window_label = f"últimos {days}d"
        else:
            pairs = resolve_window(sessions, window, cycle_start=plan_cfg.cycle_start)
            window_label = f"janela={window}"
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(2)

    if not pairs:
        console.print(f"[yellow]Sem turns na janela ({window_label}).[/yellow]")
        return

    aggs = aggregate_by_model(pairs)[:limit]
    total = total_credits(pairs)

    header = Text()
    header.append(f"{window_label}  ", style="bold")
    header.append(f"{_fmt_credits(total)} créditos", style="bold green")
    console.print(Panel(header, title="Modelos", expand=False))
    console.print(_aggregates_table("Por modelo", aggs, "modelo"))
```

E adicionar imports:

```python
from kiro_dash.aggregator import (
    # ... já existentes ...
    aggregate_by_project,
    resolve_window,
)
```

- [ ] **Step 4: Substituir uso de `aggregate_by_cwd` pela versão `_by_project` em `today`**

Localizar a função `today` e trocar:

```python
console.print(_aggregates_table("Por projeto (cwd)", aggregate_by_cwd(pairs), "cwd"))
```

por:

```python
console.print(_aggregates_table("Por projeto", aggregate_by_project(pairs), "projeto"))
```

(Deixa `aggregate_by_cwd` no aggregator como existente — não mexer; quem importa é `aggregate_by_project` agora.)

- [ ] **Step 5: Rodar — passa**

```bash
pytest tests/test_cli_projects_models_recent.py -v
pytest tests/ -v   # todos os testes
```

Expected: todos verdes.

- [ ] **Step 6: Smoke manual**

```bash
kiro-dash projects --window today
kiro-dash projects --window month
kiro-dash projects --window cycle
kiro-dash projects --window all
kiro-dash models --window 14
```

Expected: cada um exibe agregação correta. Window inválida rejeita com erro.

- [ ] **Step 7: Commit**

```bash
git add src/kiro_dash/cli.py tests/test_cli_projects_models_recent.py
git commit -m "feat(cli): --window today/week/month/cycle/all em projects/models e by_project em today"
```

---

### Task 4: Atualizar Tabs F (`projects_tab`, `models_tab`) para usar heurística

**Files:**
- Modify: `src/kiro_dash/views/tabs/projects_tab.py`
- Modify: `src/kiro_dash/views/tabs/models_tab.py`

> **Pré-requisito:** Frente F mergeada antes desta task.

- [ ] **Step 1: Em `projects_tab.py`, trocar `aggregate_by_cwd` por `aggregate_by_project`**

```python
from kiro_dash.aggregator import (
    Aggregate,
    aggregate_by_project,
    turns_in_last_days,
)

# em build_projects_snapshot:
return ProjectsSnapshot(window_days=days, aggs=aggregate_by_project(pairs))
```

E ajuste a coluna do DataTable: `"projeto"` em vez de `"projeto (cwd)"`.

- [ ] **Step 2: Smoke da TUI**

```bash
kiro-dash tui
# pressionar 3 (Projects) — labels devem aparecer consolidados
```

- [ ] **Step 3: Commit**

```bash
git add src/kiro_dash/views/tabs/projects_tab.py
git commit -m "feat(tui): ProjectsTab usa heurística project_label"
```

---

### Task 5: Documentação no README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Atualizar seção "Uso" e adicionar seção "Mapeamento de projetos"**

Adicionar antes da Licença:

```markdown
## Mapeamento de projetos (heurística)

O `kiro-dash` consolida sessões em "projetos conceituais" mapeando o
`cwd` da sessão em um label. Regras (na ordem):

| Padrão de path | Label |
|---|---|
| `~/iris/projetos/<categoria>/<projeto>/...` (categorias: pessoal, profissional, institucional, concluidos) | `<categoria>/<projeto>` |
| `~/iris/projetos/normativos/...` | `iris-normativos` |
| `~/iris/projetos/referencias/...` | `iris-referencias` |
| `~/iris/projetos/...` (sem categoria) | `iris-projetos` |
| `~/iris/...` | `iris-geral` |
| `~/Desenvolvimento/ifsp/<grupo>/<repo>/...` | `ifsp/<grupo>/<repo>` |
| `~/Desenvolvimento/<conta>/<repo>/...` | `<conta>/<repo>` |
| `~/nyx/...` | `nyx` |
| Outros sob `~` | path relativo ao home |
| Fora do home | path literal |

Override declarativo (`config.toml` com aliases custom) está planejado
para Wave 3.

## Filtros temporais

Comandos `today`, `projects` e `models` aceitam `--window`:

```bash
kiro-dash projects --window today        # só hoje
kiro-dash projects --window week         # últimos 7 dias (default)
kiro-dash projects --window month        # últimos 30 dias
kiro-dash projects --window cycle        # desde cycle_start do plano
kiro-dash projects --window all          # tudo desde sempre
kiro-dash projects --window 14           # últimos 14 dias
```

`--days N` segue funcionando como atalho legacy (override de `--window`).
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs(project): heurística + filtros temporais documentados"
```

---

## Self-Review Checklist

- [ ] 19 testes da heurística cobrem todas as 9 regras + edge cases
- [ ] `aggregate_by_project` consolida sub-cwds corretamente
- [ ] `resolve_window` aceita string/int e rejeita valores não-reconhecidos
- [ ] CLI honra `--days` legacy e `--window` novo, sem ambiguidade
- [ ] `today` agora usa heurística (sub-cwds consolidados)
- [ ] TUI ProjectsTab usa heurística
- [ ] README documenta as regras e os valores de `--window`

## Done When

- `pytest tests/test_project.py tests/test_window_resolver.py tests/test_aggregator.py tests/test_cli_projects_models_recent.py -v` → todos passam
- Smoke manual: `kiro-dash projects --window cycle` mostra labels consolidados (ex: `institucional/auto-normas` ao invés de 3 paths)
- 5 commits no branch `feat/wave2-projects-windows`
