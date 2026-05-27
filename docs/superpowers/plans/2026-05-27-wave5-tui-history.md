# Wave 5 / Frente O — TUI History tab + comparativos Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Adicionar **aba History** à TUI (atalho `7`) com série temporal de uso e três blocos comparativos: **hoje × ontem**, **semana atual × semana passada**, **mês × mês passado** e **ano × ano passado**. Visual: sparklines de 30/365 dias, bar charts comparativos.

**Architecture:**

- Nova `HistoryTab` com 3 seções:
  1. **Sparkline 30 dias** (créditos/dia)
  2. **Sparkline 12 meses** (créditos/mês)
  3. **Comparativos** em grid (4 painéis lado a lado: hoje × ontem, semana × semana passada, mês × mês passado, ano × ano passado)
- Refresh manual (tecla `r`), igual outras abas exceto Now.
- Reusa `PeriodSummary`, `month_summary`, `year_summary`, `diff_summaries` da Frente N.
- Reusa `sparkline()` da Frente K.

**Tech Stack:** Python 3.12, Textual (já dep), Rich.

**Branch:** `feat/wave5-tui-history`

**Pré-requisitos:** Frentes L, M, N mergeadas.

---

## File Structure

| Arquivo | Responsabilidade | Mudança |
|---|---|---|
| `src/kiro_dash/views/tabs/history_tab.py` | Widget HistoryTab | **Criar** |
| `src/kiro_dash/views/app.py` | Adicionar `TabPane` History (atalho `7`) | **Modificar** |
| `src/kiro_dash/views/styles.tcss` | CSS pra HistoryTab (grid de 4 cards) | **Modificar** |
| `tests/test_views_history.py` | Smoke da aba | **Criar** |

---

### Task 1: Estrutura básica da aba + sparkline 30d/12m

**Files:**
- Create: `src/kiro_dash/views/tabs/history_tab.py`
- Modify: `src/kiro_dash/views/app.py`
- Modify: `src/kiro_dash/views/styles.tcss`

- [ ] **Step 1: HistoryTab esqueleto**

```python
"""Aba History — série temporal + comparativos.

Refresh manual (igual outras abas exceto Now).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import DataTable, Static

from kiro_dash.history import (
    PeriodSummary, diff_summaries, month_summary, year_summary,
)
from kiro_dash.snapshots import read_snapshot
from kiro_dash.visual import bar_inline, sparkline


@dataclass(frozen=True, slots=True)
class HistorySnapshot:
    daily_30d: list[float] = field(default_factory=list)  # créditos/dia, mais antigo → mais novo
    monthly_12: list[float] = field(default_factory=list)
    today_vs_yesterday: dict | None = None
    week_vs_lastweek: dict | None = None
    month_vs_lastmonth: dict | None = None
    year_vs_lastyear: dict | None = None


def build_history_snapshot() -> HistorySnapshot:
    today = datetime.now().astimezone().date()

    # 30 dias diários
    daily = []
    for offset in range(29, -1, -1):
        d = today - timedelta(days=offset)
        snap = read_snapshot(d)
        daily.append(snap["totals"]["credits"] if snap else 0.0)

    # 12 meses (atual + 11 anteriores)
    monthly = []
    cursor = today.replace(day=1)
    months_back = []
    for _ in range(12):
        months_back.append((cursor.year, cursor.month))
        # Mês anterior
        if cursor.month == 1:
            cursor = cursor.replace(year=cursor.year - 1, month=12)
        else:
            cursor = cursor.replace(month=cursor.month - 1)
    months_back.reverse()
    for y, m in months_back:
        s = month_summary(y, m)
        monthly.append(s.credits)

    # Comparativos
    # ... (Task 2)
    return HistorySnapshot(
        daily_30d=daily,
        monthly_12=monthly,
        today_vs_yesterday=None,  # preencher na Task 2
        week_vs_lastweek=None,
        month_vs_lastmonth=None,
        year_vs_lastyear=None,
    )


class HistoryTab(Container):
    """Aba History — série temporal + 4 comparativos."""

    def compose(self) -> ComposeResult:
        yield Static(id="history-header")
        yield Static(id="history-spark30")
        yield Static(id="history-spark12m")
        yield Static(id="history-compare-grid")  # placeholder; Task 2

    def on_mount(self) -> None:
        self.refresh_snapshot()

    def refresh_snapshot(self) -> None:
        snap = build_history_snapshot()
        self.query_one("#history-header", Static).update(
            "[b]Histórico[/b] — séries temporais e comparativos "
            "[dim](pressione 'r' para atualizar)[/dim]"
        )

        spark30 = sparkline(snap.daily_30d, max_chars=30)
        peak_30 = max(snap.daily_30d) if snap.daily_30d else 0
        self.query_one("#history-spark30", Static).update(
            f"[b]30 dias[/b] (créditos/dia, pico {peak_30:.0f}):\n"
            f"  {spark30}"
        )

        spark12 = sparkline(snap.monthly_12, max_chars=12)
        peak_12 = max(snap.monthly_12) if snap.monthly_12 else 0
        self.query_one("#history-spark12m", Static).update(
            f"[b]12 meses[/b] (créditos/mês, pico {peak_12:.0f}):\n"
            f"  {spark12}"
        )
```

- [ ] **Step 2: Adicionar tab no app.py**

```python
# em KiroDashApp.compose, antes de Footer:
with TabPane("History", id="history"):
    yield HistoryTab()

# Bindings (acrescentar):
Binding("7", "show_tab('history')", "History"),
```

- [ ] **Step 3: CSS**

Em `styles.tcss`:

```css
HistoryTab Static {
    width: 100%;
    margin: 0 1;
    padding: 0 1;
}

#history-spark30, #history-spark12m {
    height: auto;
    margin-bottom: 1;
}

#history-compare-grid {
    height: 1fr;
}
```

- [ ] **Step 4: Smoke**

```bash
kiro-dash tui
# pressionar 7
```

Validar visual: sparklines de 30d e 12m aparecem.

- [ ] **Step 5: Commit**

```bash
git add src/kiro_dash/views/tabs/history_tab.py src/kiro_dash/views/app.py src/kiro_dash/views/styles.tcss
git -c user.email='leonardo.menzani@gmail.com' -c user.name='mencoding' \
  commit -m "feat(tui): aba History com sparklines de 30 dias e 12 meses"
```

---

### Task 2: Comparativos hoje/ontem, semana, mês, ano

**Files:**
- Modify: `src/kiro_dash/views/tabs/history_tab.py`

- [ ] **Step 1: Estender `build_history_snapshot` com 4 comparativos**

```python
def build_history_snapshot() -> HistorySnapshot:
    # ...código existente acima...

    # Comparativos — usar funções da Frente N
    from kiro_dash.cli import _live_day_as_period, _live_window_as_period

    a_today = _live_day_as_period(today, label="hoje")
    b_yesterday = _live_day_as_period(today - timedelta(days=1), label="ontem")
    todvy = diff_summaries(a_today, b_yesterday)

    a_week = _live_window_as_period(today, days=7, label="última semana")
    b_week = _live_window_as_period(today - timedelta(days=7), days=7, label="semana anterior")
    weekvw = diff_summaries(a_week, b_week)

    cur_m = month_summary(today.year, today.month)
    prev_m_date = today.replace(day=1) - timedelta(days=1)
    prev_m = month_summary(prev_m_date.year, prev_m_date.month)
    monvm = diff_summaries(cur_m, prev_m)

    cur_y = year_summary(today.year)
    prev_y = year_summary(today.year - 1)
    yrvy = diff_summaries(cur_y, prev_y)

    return HistorySnapshot(
        daily_30d=daily,
        monthly_12=monthly,
        today_vs_yesterday=todvy,
        week_vs_lastweek=weekvw,
        month_vs_lastmonth=monvm,
        year_vs_lastyear=yrvy,
    )
```

- [ ] **Step 2: Renderizar grid 2x2 de comparativos**

Atualizar `compose` da `HistoryTab`:

```python
def compose(self) -> ComposeResult:
    yield Static(id="history-header")
    yield Static(id="history-spark30")
    yield Static(id="history-spark12m")
    with Horizontal(id="history-compare-row1"):
        yield Static(id="cmp-today", classes="cmp-card")
        yield Static(id="cmp-week", classes="cmp-card")
    with Horizontal(id="history-compare-row2"):
        yield Static(id="cmp-month", classes="cmp-card")
        yield Static(id="cmp-year", classes="cmp-card")
```

E em `refresh_snapshot`:

```python
def _render_cmp(diff, title):
    if diff is None:
        return f"[b]{title}[/b]\n[dim]sem dados[/dim]"
    a, b = diff["a_label"], diff["b_label"]
    cred_a, cred_b = diff["credits_a"], diff["credits_b"]
    delta = diff["credits_delta"]
    pct = diff.get("credits_pct")
    delta_style = "green" if delta >= 0 else "red"
    pct_str = f"({pct*100:+.1f}%)" if pct is not None else ""
    bar = bar_inline(min(1.0, abs(delta) / max(cred_a, cred_b, 1)), width=14)
    return (
        f"[b]{title}[/b]\n"
        f"  {a:<14}: {cred_a:>10.2f}\n"
        f"  {b:<14}: {cred_b:>10.2f}\n"
        f"  Δ: [{delta_style}]{delta:+.2f}[/{delta_style}] {pct_str}\n"
        f"  {bar}"
    )

self.query_one("#cmp-today", Static).update(
    _render_cmp(snap.today_vs_yesterday, "Hoje × Ontem")
)
self.query_one("#cmp-week", Static).update(
    _render_cmp(snap.week_vs_lastweek, "Semana × Sem. anterior")
)
self.query_one("#cmp-month", Static).update(
    _render_cmp(snap.month_vs_lastmonth, "Mês × Mês anterior")
)
self.query_one("#cmp-year", Static).update(
    _render_cmp(snap.year_vs_lastyear, "Ano × Ano anterior")
)
```

- [ ] **Step 3: CSS pros cards**

```css
.cmp-card {
    width: 1fr;
    height: 8;
    margin: 0 1;
    padding: 0 1;
    border: round $primary;
}
```

- [ ] **Step 4: Tests headless**

Criar `tests/test_views_history.py`:

```python
import pytest
from textual.widgets import TabbedContent

from kiro_dash.views.app import KiroDashApp


@pytest.mark.asyncio
async def test_history_tab_renders():
    app = KiroDashApp()
    async with app.run_test() as pilot:
        await pilot.press("7")
        await pilot.pause()
        tabbed = pilot.app.query_one(TabbedContent)
        assert tabbed.active == "history"


@pytest.mark.asyncio
async def test_history_tab_refresh_doesnt_crash():
    app = KiroDashApp()
    async with app.run_test() as pilot:
        await pilot.press("7")
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause()
```

- [ ] **Step 5: Smoke**

```bash
kiro-dash tui
# 7 → ver sparklines + 4 cards de comparativo
```

- [ ] **Step 6: Commit**

```bash
git add src/kiro_dash/views/tabs/history_tab.py src/kiro_dash/views/styles.tcss tests/test_views_history.py
git -c user.email='leonardo.menzani@gmail.com' -c user.name='mencoding' \
  commit -m "feat(tui): comparativos hoje/semana/mês/ano em grid 2x2"
```

---

### Task 3: README + bump v0.6.0

**Files:**
- Modify: `README.md`
- Modify: `src/kiro_dash/__init__.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: README — seção `History`**

```markdown
## Aba History (TUI)

Atalho `7`. Mostra:

- **Sparkline de 30 dias** — créditos/dia
- **Sparkline de 12 meses** — créditos/mês
- **4 cards comparativos** em grid 2×2:
  - Hoje × ontem
  - Semana atual × semana passada
  - Mês corrente × mês anterior
  - Ano corrente × ano anterior

Cada card mostra créditos absolutos, delta e percentual de variação,
com cor (verde=cresce, vermelho=cai).

Snapshot reconstruído sob demanda via `kiro_dash.history` (sem cache).
Refresh manual via tecla `r`.
```

- [ ] **Step 2: Bump v0.6.0 + tag**

```bash
# __init__.py
__version__ = "0.6.0"
# pyproject.toml
version = "0.6.0"
```

- [ ] **Step 3: Commit + tag**

```bash
git add README.md src/kiro_dash/__init__.py pyproject.toml
git -c user.email='leonardo.menzani@gmail.com' -c user.name='mencoding' \
  commit -m "chore: bump v0.6.0

Wave 5 — persistência histórica:
- Frente L: Clock injetável (now=) em todas as funções de janela
- Frente M: snapshots diários multi-host com lazy + self-healing
- Frente N: queries históricas (today --day, month, year, compare)
- Frente O: aba TUI History com sparklines 30d/12m e 4 comparativos"
git tag v0.6.0
```

---

## Self-Review Checklist

- [ ] `HistoryTab` reusa `sparkline` da Frente K
- [ ] Comparativos usam `diff_summaries` da Frente N
- [ ] Sparkline de 30 dias = `daily_30d` ordenado mais antigo → novo
- [ ] Cores: verde quando delta ≥ 0, vermelho quando < 0
- [ ] Refresh manual via `r` igual outras abas
- [ ] CSS escopa estilos com `HistoryTab` para evitar contaminar outras abas
- [ ] App.run_test() valida bind `7` e `r` sem crash

## Done When

- `pytest tests/test_views_history.py -v` → todos verdes
- TUI: aba 7 mostra sparklines + 4 cards (mesmo com 0 dados — gracefully)
- Refresh `r` na aba não trava
- 3 commits + tag v0.6.0 no branch `feat/wave5-tui-history`
