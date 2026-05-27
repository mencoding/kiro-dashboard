# Wave 5 / Frente N — Queries históricas Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Habilitar consultas a dias, meses, anos passados via snapshots persistidos. `today --day YYYY-MM-DD` agora consulta snapshot quando data é antiga; comandos novos `month` / `year` reconstroem agregações via cascata de snapshots; `compare` faz diff entre dois períodos.

**Architecture:**

- **Híbrido stateful/stateless:**
  - Hoje e ontem (D, D-1): re-lê dos `.json` originais (igual antes)
  - D-2 e anterior: lê snapshot
- **Reconstrução mensal/anual:** soma snapshots diários do range. Sem cache mensal — recalcular 31 lookups é trivial.
- **Comparativos hoje/ontem usam dados live; comparativos de período (mês/ano) leem snapshots.**

**Tech Stack:** Python 3.12 stdlib + Rich.

**Branch:** `feat/wave5-history-queries`

**Pré-requisitos:** Frentes L (Clock) e M (snapshot) mergeadas.

---

## File Structure

| Arquivo | Responsabilidade | Mudança |
|---|---|---|
| `src/kiro_dash/history.py` | Reconstrução cascata snapshot diário → mensal/anual | **Criar** |
| `src/kiro_dash/cli.py` | `today --day` lê snapshot + comandos `month`/`year`/`compare` | **Modificar** |
| `tests/test_history.py` | Cobertura | **Criar** |
| `tests/test_history_commands.py` | Smoke CLI | **Criar** |
| `README.md` | Seção "Queries históricas" | **Modificar** |

---

### Task 1: Reconstrução `month_summary` e `year_summary`

**Files:**
- Create: `src/kiro_dash/history.py`
- Create: `tests/test_history.py`

- [ ] **Step 1: Escrever testes**

```python
"""Reconstrução de resumos por período (mês, ano) a partir de snapshots."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from kiro_dash.history import (
    PeriodSummary,
    diff_summaries,
    month_summary,
    year_summary,
)
from kiro_dash.snapshots import SnapshotPaths


def _write_fake_snapshot(paths: SnapshotPaths, d: date, host: str, *,
                         credits: float, turns: int, sessions: int):
    paths.root.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "local_date": d.isoformat(),
        "tz_offset": "-03:00",
        "captured_at": "2026-05-17T03:00:00Z",
        "captured_by_host": host,
        "totals": {"credits": credits, "turns": turns, "sessions": sessions},
        "by_model": [{"label": "claude-opus-4.7", "credits": credits,
                      "turns": turns, "sessions": sessions,
                      "duration_secs": 0, "tool_uses": 0}],
        "by_project": [], "by_agent_pair": [], "by_session": [], "by_tool": [],
    }
    with open(paths.for_date(d, host), "w") as f:
        json.dump(payload, f)


def test_month_summary_soma_dias_existentes(tmp_path):
    paths = SnapshotPaths(root=tmp_path)
    _write_fake_snapshot(paths, date(2026, 5, 1), "h1", credits=10, turns=2, sessions=1)
    _write_fake_snapshot(paths, date(2026, 5, 2), "h1", credits=20, turns=4, sessions=2)
    _write_fake_snapshot(paths, date(2026, 5, 15), "h1", credits=5, turns=1, sessions=1)

    summary = month_summary(2026, 5, paths=paths)
    assert summary.credits == 35
    assert summary.turns == 7
    assert summary.days_with_data == 3
    assert summary.period_label == "2026-05"


def test_month_summary_dias_sem_dados_n_quebram(tmp_path):
    paths = SnapshotPaths(root=tmp_path)
    summary = month_summary(2026, 5, paths=paths)
    assert summary.credits == 0
    assert summary.days_with_data == 0


def test_year_summary_agrega_meses(tmp_path):
    paths = SnapshotPaths(root=tmp_path)
    _write_fake_snapshot(paths, date(2026, 1, 1), "h1", credits=10, turns=1, sessions=1)
    _write_fake_snapshot(paths, date(2026, 6, 15), "h1", credits=20, turns=2, sessions=1)
    _write_fake_snapshot(paths, date(2026, 12, 31), "h1", credits=30, turns=3, sessions=1)

    summary = year_summary(2026, paths=paths)
    assert summary.credits == 60
    assert summary.turns == 6
    assert summary.days_with_data == 3
    assert summary.period_label == "2026"


def test_diff_summaries():
    a = PeriodSummary(period_label="2026-05", credits=100, turns=20,
                      sessions=10, days_with_data=15, by_model=[])
    b = PeriodSummary(period_label="2026-04", credits=80, turns=15,
                      sessions=8, days_with_data=12, by_model=[])
    diff = diff_summaries(a, b)
    assert diff["credits_delta"] == 20
    assert diff["credits_pct"] == pytest.approx(0.25)  # 25% growth
    assert diff["turns_delta"] == 5
```

- [ ] **Step 2: Rodar — falha**

- [ ] **Step 3: Implementar**

```python
"""Reconstrução de resumos por período via cascata de snapshots diários.

Sem cache mensal/anual — recalcular 31 ou 365 lookups é trivial e mantém
a fonte de verdade única (os snapshots diários).
"""
from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from kiro_dash.snapshots import SnapshotPaths, read_snapshot


@dataclass(frozen=True, slots=True)
class PeriodSummary:
    period_label: str  # ex: "2026-05" ou "2026"
    credits: float
    turns: int
    sessions: int
    days_with_data: int
    by_model: list[dict] = field(default_factory=list)
    by_project: list[dict] = field(default_factory=list)
    by_tool: list[dict] = field(default_factory=list)


def _aggregate_breakdown(snaps: list[dict], key: str) -> list[dict]:
    """Re-agrega ``by_X`` somando entries com mesmo ``label`` ou identificador."""
    bucket: dict[str, dict] = defaultdict(
        lambda: {"credits": 0.0, "turns": 0, "sessions": 0,
                 "duration_secs": 0, "tool_uses": 0}
    )
    label_field = "name" if key == "by_tool" else "label"
    for snap in snaps:
        for item in snap.get(key, []):
            label = item.get(label_field, "?")
            for f in ("credits", "turns", "sessions", "duration_secs",
                      "tool_uses", "count", "errors"):
                if f in item:
                    bucket[label][f] = bucket[label].get(f, 0) + item[f]
    out = []
    for label, vals in bucket.items():
        entry = {label_field: label}
        entry.update(vals)
        out.append(entry)
    out.sort(key=lambda x: x.get("credits", x.get("count", 0)), reverse=True)
    return out


def month_summary(
    year: int,
    month: int,
    *,
    paths: SnapshotPaths | None = None,
) -> PeriodSummary:
    """Soma todos os snapshots disponíveis do mês."""
    days_in_month = calendar.monthrange(year, month)[1]
    snaps = []
    for d in range(1, days_in_month + 1):
        snap = read_snapshot(date(year, month, d), paths=paths)
        if snap is not None:
            snaps.append(snap)
    return _build_summary(snaps, label=f"{year:04d}-{month:02d}")


def year_summary(
    year: int,
    *,
    paths: SnapshotPaths | None = None,
) -> PeriodSummary:
    """Soma todos os snapshots disponíveis do ano."""
    snaps = []
    d = date(year, 1, 1)
    while d.year == year:
        snap = read_snapshot(d, paths=paths)
        if snap is not None:
            snaps.append(snap)
        d += timedelta(days=1)
    return _build_summary(snaps, label=str(year))


def _build_summary(snaps: list[dict], *, label: str) -> PeriodSummary:
    if not snaps:
        return PeriodSummary(period_label=label, credits=0, turns=0,
                             sessions=0, days_with_data=0)
    return PeriodSummary(
        period_label=label,
        credits=round(sum(s["totals"]["credits"] for s in snaps), 4),
        turns=sum(s["totals"]["turns"] for s in snaps),
        sessions=sum(s["totals"]["sessions"] for s in snaps),
        days_with_data=len(snaps),
        by_model=_aggregate_breakdown(snaps, "by_model"),
        by_project=_aggregate_breakdown(snaps, "by_project"),
        by_tool=_aggregate_breakdown(snaps, "by_tool"),
    )


def diff_summaries(
    a: PeriodSummary,
    b: PeriodSummary,
) -> dict[str, Any]:
    """Compara ``a`` vs ``b`` (a - b). Retorna dict com deltas e percentuais."""
    def pct(a_v, b_v):
        return (a_v - b_v) / b_v if b_v != 0 else None
    return {
        "a_label": a.period_label,
        "b_label": b.period_label,
        "credits_a": a.credits,
        "credits_b": b.credits,
        "credits_delta": a.credits - b.credits,
        "credits_pct": pct(a.credits, b.credits),
        "turns_delta": a.turns - b.turns,
        "turns_pct": pct(a.turns, b.turns),
        "sessions_delta": a.sessions - b.sessions,
        "days_a": a.days_with_data,
        "days_b": b.days_with_data,
    }
```

- [ ] **Step 4: Rodar — passa**

- [ ] **Step 5: Commit**

```bash
git add src/kiro_dash/history.py tests/test_history.py
git -c user.email='leonardo.menzani@gmail.com' -c user.name='mencoding' \
  commit -m "feat(history): month_summary, year_summary, diff_summaries"
```

---

### Task 2: `today --day` lê snapshot quando antigo

**Files:**
- Modify: `src/kiro_dash/cli.py`
- Create/modify: tests CLI

- [ ] **Step 1: Modificar `today`**

```python
@main.command()
@click.option("--day", "day_str", default=None,
              help="Dia em formato YYYY-MM-DD (default: hoje, local).")
@click.option("--agent", default=None, help="Filtra por agent_name.")
def today(day_str: str | None, agent: str | None) -> None:
    d = date.fromisoformat(day_str) if day_str else datetime.now().astimezone().date()
    today_local = datetime.now().astimezone().date()

    # Snapshot path: dia <= D-2
    if d <= today_local - timedelta(days=2):
        from kiro_dash.snapshots import read_snapshot
        snap = read_snapshot(d)
        if snap is None:
            console.print(f"[yellow]Sem snapshot para {d}. "
                          f"Tente: kiro-dash snapshot {d}[/yellow]")
            return
        _render_snapshot(snap, agent=agent)
        return

    # Path stateless (atual): D ou D-1
    sessions = load_all_sessions()
    pairs = filter_by_agent(turns_in_local_day(sessions, d), agent)
    if not pairs:
        console.print(f"[yellow]Nenhum turn em {d}.[/yellow]")
        return
    # ... resto do today atual
```

`_render_snapshot(snap, agent=None)` renderiza o JSON do snapshot no mesmo formato visual do today. Reusar helpers `_aggregates_table` etc.

- [ ] **Step 2: Smoke**

```bash
# Hoje (live)
kiro-dash today
# Ontem (live)
kiro-dash today --day $(date -d "yesterday" +%Y-%m-%d)
# Anteontem (snapshot, pode falhar se sem snapshot)
kiro-dash today --day $(date -d "2 days ago" +%Y-%m-%d)
```

- [ ] **Step 3: Commit**

```bash
git add src/kiro_dash/cli.py
git -c user.email='leonardo.menzani@gmail.com' -c user.name='mencoding' \
  commit -m "feat(cli): today --day < D-2 lê snapshot"
```

---

### Task 3: Comandos `month`, `year`

**Files:**
- Modify: `src/kiro_dash/cli.py`
- Create: `tests/test_history_commands.py`

- [ ] **Step 1: Implementar `month`**

```python
@main.command()
@click.argument("month_str", required=False)
def month(month_str: str | None) -> None:
    """Resumo mensal de uso (lê snapshots).

    ``month_str``: YYYY-MM (default: mês corrente).
    """
    if month_str is None:
        today = datetime.now().astimezone().date()
        year, m = today.year, today.month
    else:
        try:
            year, m = map(int, month_str.split("-"))
        except (ValueError, AttributeError):
            console.print(f"[red]Formato inválido: '{month_str}'. Use YYYY-MM.[/red]")
            raise SystemExit(2)
        if not (1 <= m <= 12):
            console.print(f"[red]Mês inválido: {m}.[/red]")
            raise SystemExit(2)

    from kiro_dash.history import month_summary
    summary = month_summary(year, m)
    _render_period_summary(summary)


@main.command()
@click.argument("year_str", required=False)
def year(year_str: str | None) -> None:
    """Resumo anual de uso (lê snapshots)."""
    if year_str is None:
        y = datetime.now().astimezone().year
    else:
        try:
            y = int(year_str)
        except ValueError:
            console.print(f"[red]Ano inválido: '{year_str}'.[/red]")
            raise SystemExit(2)

    from kiro_dash.history import year_summary
    summary = year_summary(y)
    _render_period_summary(summary)


def _render_period_summary(s) -> None:
    """Header + breakdowns do PeriodSummary."""
    if s.days_with_data == 0:
        console.print(f"[yellow]Sem snapshots no período {s.period_label}.[/yellow]")
        return
    header = Text()
    header.append(f"{s.period_label}  ", style="bold")
    header.append(f"{_fmt_credits(s.credits)} créditos  ", style="bold green")
    header.append(f"{s.turns} turns / {s.sessions} sessões  ")
    header.append(f"({s.days_with_data} dias com dados)", style="dim")
    console.print(Panel(header, title="Resumo", expand=False))

    if s.by_model:
        t = Table(title="Por modelo", expand=False, header_style="bold")
        for col in ("modelo", "créditos", "turns", "sessões"):
            t.add_column(col)
        for m in s.by_model:
            t.add_row(m["label"], _fmt_credits(m["credits"]),
                      str(m["turns"]), str(m["sessions"]))
        console.print(t)
    # idem para by_project, by_tool
```

- [ ] **Step 2: Tests CLI**

```python
def test_month_command_sem_snapshots_avisa(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(main, ["month", "2026-01"])
    assert result.exit_code == 0
    assert "sem snapshots" in result.output.lower()


def test_year_command_aceita_atalho_sem_arg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(main, ["year"])
    assert result.exit_code == 0
```

- [ ] **Step 3: Commit**

---

### Task 4: Comando `compare` (mês vs mês, ano vs ano)

**Files:**
- Modify: `src/kiro_dash/cli.py`
- Modify: `tests/test_history_commands.py`

- [ ] **Step 1: Implementar `compare`**

```python
@main.command()
@click.argument("a_str")
@click.argument("b_str")
def compare(a_str: str, b_str: str) -> None:
    """Compara dois períodos. Aceita YYYY (ano) ou YYYY-MM (mês).

    Exemplos::

        kiro-dash compare 2026-05 2026-04        # mês × mês
        kiro-dash compare 2026 2025              # ano × ano
        kiro-dash compare today yesterday        # comparativo live
        kiro-dash compare week last-week
    """
    from kiro_dash.history import (
        diff_summaries, month_summary, year_summary,
    )

    a = _resolve_period(a_str)
    b = _resolve_period(b_str)
    if a is None or b is None:
        console.print(f"[red]Período inválido. Use YYYY, YYYY-MM, today/yesterday/week/last-week.[/red]")
        raise SystemExit(2)

    diff = diff_summaries(a, b)
    table = Table(title=f"{a.period_label} vs {b.period_label}",
                  expand=False, header_style="bold")
    table.add_column("métrica")
    table.add_column(a.period_label, justify="right")
    table.add_column(b.period_label, justify="right")
    table.add_column("Δ", justify="right")
    table.add_column("%", justify="right")

    for name, fa, fb, fd in [
        ("créditos", a.credits, b.credits, diff["credits_delta"]),
        ("turns", a.turns, b.turns, diff["turns_delta"]),
        ("sessões", a.sessions, b.sessions, diff["sessions_delta"]),
    ]:
        pct_str = f"{(fd/fb)*100:+.1f}%" if fb else "—"
        delta_style = "green" if fd >= 0 else "red"
        table.add_row(name, str(fa), str(fb),
                      Text(f"{fd:+}", style=delta_style), pct_str)
    console.print(table)


def _resolve_period(s: str):
    """Converte string ('2026-05', 'today', 'week', etc.) em PeriodSummary."""
    from kiro_dash.history import month_summary, year_summary
    s = s.strip().lower()
    today = datetime.now().astimezone().date()

    if s == "today":
        # Construir PeriodSummary live de hoje
        return _live_day_as_period(today, label="hoje")
    if s == "yesterday":
        return _live_day_as_period(today - timedelta(days=1), label="ontem")
    if s == "week":
        return _live_window_as_period(today, days=7, label="última semana")
    if s == "last-week":
        return _live_window_as_period(today - timedelta(days=7), days=7, label="semana anterior")
    if s == "month":
        return month_summary(today.year, today.month)
    if s == "last-month":
        prev = today.replace(day=1) - timedelta(days=1)
        return month_summary(prev.year, prev.month)
    if s == "year":
        return year_summary(today.year)
    if s == "last-year":
        return year_summary(today.year - 1)

    # YYYY-MM
    if len(s) == 7 and s[4] == "-":
        try:
            year, m = int(s[:4]), int(s[5:])
            return month_summary(year, m)
        except ValueError:
            return None
    # YYYY
    if len(s) == 4 and s.isdigit():
        return year_summary(int(s))

    return None


def _live_day_as_period(d, *, label):
    """Constrói PeriodSummary lendo turns live de um dia (D ou D-1)."""
    from kiro_dash.history import PeriodSummary
    sessions = load_all_sessions()
    pairs = turns_in_local_day(sessions, d)
    return PeriodSummary(
        period_label=label,
        credits=round(total_credits(pairs), 4),
        turns=len(pairs),
        sessions=len({s.session_id for s, _ in pairs}),
        days_with_data=1 if pairs else 0,
        by_model=[], by_project=[], by_tool=[],
    )


def _live_window_as_period(start_day, *, days, label):
    """PeriodSummary acumulado em janela contígua (live + snapshots)."""
    # ...análogo, lendo cada dia: live se hoje/ontem; senão snapshot.
    ...
```

- [ ] **Step 2: Tests**

```python
def test_compare_today_yesterday_runs():
    runner = CliRunner()
    with patch("kiro_dash.cli.load_all_sessions", return_value=[]):
        result = runner.invoke(main, ["compare", "today", "yesterday"])
    assert result.exit_code == 0
    assert "hoje" in result.output.lower()
    assert "ontem" in result.output.lower()


def test_compare_invalid_period_falha():
    runner = CliRunner()
    result = runner.invoke(main, ["compare", "xyz", "2026"])
    assert result.exit_code != 0
```

- [ ] **Step 3: Commit**

```bash
git add src/kiro_dash/cli.py tests/test_history_commands.py
git -c user.email='leonardo.menzani@gmail.com' -c user.name='mencoding' \
  commit -m "feat(cli): compare entre períodos (today/yesterday/week/month/year)"
```

---

### Task 5: README

```markdown
## Queries históricas

```bash
kiro-dash today --day 2026-05-16        # snapshot ou live (D, D-1)
kiro-dash month                         # mês corrente
kiro-dash month 2026-05
kiro-dash year                          # ano corrente
kiro-dash year 2026

kiro-dash compare today yesterday
kiro-dash compare week last-week
kiro-dash compare 2026-05 2026-04
kiro-dash compare 2026 2025
```

Comandos `month`/`year`/`compare` agregam snapshots diários sob demanda.
Sem cache mensal — fonte única de verdade são os snapshots de dia.

Ranges sem snapshot (dias antes da instalação ou da primeira execução)
mostram zero. Use `kiro-dash snapshot` pra gerar manualmente.
```

---

## Self-Review Checklist

- [ ] `today --day` decide snapshot vs live por idade da data
- [ ] `month`/`year` retornam zero gracefully quando sem dados
- [ ] `compare` funciona com `today`/`yesterday` (live) e períodos passados (snapshot)
- [ ] `_resolve_period` cobre: today, yesterday, week, last-week, month, last-month, year, last-year, YYYY, YYYY-MM
- [ ] Reagregação de `by_model`/`by_project`/`by_tool` consolida labels iguais
- [ ] README documenta todos os comandos e formatos

## Done When

- `pytest tests/test_history.py tests/test_history_commands.py -v` → todos verdes
- `kiro-dash month` mostra resumo do mês corrente (ou aviso de sem dados)
- `kiro-dash compare week last-week` funciona
- 5 commits no branch `feat/wave5-history-queries`
