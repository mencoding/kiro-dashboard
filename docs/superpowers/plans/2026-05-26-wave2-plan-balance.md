# Wave 2 / Frente E — Plan config + saldo estimado Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir que o usuário declare seu plano Kiro (free/pro/pro+/power/enterprise) num arquivo de config TOML, e mostrar o **saldo estimado** (créditos consumidos vs limite mensal) com alertas visuais nas views.

**Architecture:** Módulo `config.py` lê/escreve `~/.config/kiro-dash/config.toml`. Subcomando `kiro-dash plan get/set` para conveniência. Funções de saldo em `aggregator.py` (sums por ciclo). Views `today` e novo painel `balance` exibem barra de progresso + alertas em laranja (>=80%) e vermelho (>=95%).

**Auto-detect** (consulta API Kiro com Bearer token) **fica fora desta wave** — registrado como ideia para Wave 3.

**Tech Stack:** Python 3.12 (`tomllib` nativo para leitura, `tomli_w` para escrita), Click, Rich.

**Branch:** `feat/wave2-plan-balance`

**Defaults internos** (fonte: tabela pública kiro.dev):

| tier | monthly_credits |
|---|---|
| `free` | 50 |
| `pro` | 1000 |
| `pro+` | 2000 |
| `power` | 10000 |
| `enterprise` | 99999999 (sem cap real) |

---

## File Structure

| Arquivo | Responsabilidade | Mudança |
|---|---|---|
| `src/kiro_dash/config.py` | Carregar/salvar TOML, defaults | **Criar** |
| `src/kiro_dash/aggregator.py` | Função `turns_in_cycle` + `balance_in_cycle` | **Modificar** |
| `src/kiro_dash/cli.py` | Subcomando `plan` + flag `--remaining` em `today` | **Modificar** |
| `pyproject.toml` | Dep `tomli_w>=1.0` (escrita TOML) | **Modificar** |
| `tests/test_config.py` | Round-trip + defaults | **Criar** |
| `tests/test_balance.py` | Cálculo de saldo | **Criar** |
| `tests/test_plan_command.py` | CLI smoke | **Criar** |

---

### Task 1: Módulo `config.py` com I/O do TOML

**Files:**
- Create: `src/kiro_dash/config.py`
- Create: `tests/test_config.py`
- Modify: `pyproject.toml` (adicionar dep `tomli_w`)

- [ ] **Step 1: Adicionar dep `tomli_w` ao pyproject e instalar**

Em `pyproject.toml`, em `dependencies`:

```toml
dependencies = [
    "rich>=13.7",
    "click>=8.1",
    "mcp>=1.0",
    "tomli_w>=1.0",
]
```

```bash
cd /home/menzani/Desenvolvimento/mencoding/kiro-dash
source .venv/bin/activate
pip install -q -e ".[dev]"
```

- [ ] **Step 2: Escrever testes**

Criar `tests/test_config.py`:

```python
"""Testes do módulo config — round-trip TOML + defaults por tier."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from kiro_dash.config import (
    DEFAULT_MONTHLY_CREDITS,
    PlanConfig,
    default_config_path,
    load_plan,
    save_plan,
)


def test_default_monthly_credits_for_known_tiers():
    assert DEFAULT_MONTHLY_CREDITS["free"] == 50
    assert DEFAULT_MONTHLY_CREDITS["pro"] == 1000
    assert DEFAULT_MONTHLY_CREDITS["pro+"] == 2000
    assert DEFAULT_MONTHLY_CREDITS["power"] == 10000
    assert "enterprise" in DEFAULT_MONTHLY_CREDITS


def test_load_plan_returns_default_when_file_missing(tmp_path):
    cfg_path = tmp_path / "missing.toml"
    plan = load_plan(cfg_path)
    assert plan.tier == "free"
    assert plan.monthly_credits == 50
    assert plan.cycle_start == date.today().replace(day=1)


def test_save_then_load_round_trip(tmp_path):
    cfg_path = tmp_path / "config.toml"
    original = PlanConfig(
        tier="pro+",
        monthly_credits=2500,  # override
        cycle_start=date(2026, 5, 1),
    )
    save_plan(original, cfg_path)
    loaded = load_plan(cfg_path)
    assert loaded == original


def test_save_creates_parent_dir(tmp_path):
    cfg_path = tmp_path / "deep" / "nested" / "config.toml"
    plan = PlanConfig(tier="pro", monthly_credits=1000, cycle_start=date(2026, 1, 1))
    save_plan(plan, cfg_path)
    assert cfg_path.is_file()


def test_load_uses_default_credits_when_field_missing(tmp_path):
    cfg_path = tmp_path / "partial.toml"
    cfg_path.write_text('[plan]\ntier = "pro"\n')
    plan = load_plan(cfg_path)
    assert plan.tier == "pro"
    assert plan.monthly_credits == 1000  # default da tier


def test_load_invalid_tier_falls_back_to_free(tmp_path):
    cfg_path = tmp_path / "bad.toml"
    cfg_path.write_text('[plan]\ntier = "ultraplus9000"\n')
    plan = load_plan(cfg_path)
    assert plan.tier == "free"


def test_default_config_path_is_under_xdg_config():
    p = default_config_path()
    assert "kiro-dash" in str(p)
    assert p.name == "config.toml"


def test_save_plan_writes_valid_toml(tmp_path):
    cfg_path = tmp_path / "out.toml"
    plan = PlanConfig(tier="power", monthly_credits=10000, cycle_start=date(2026, 6, 15))
    save_plan(plan, cfg_path)
    content = cfg_path.read_text()
    assert '[plan]' in content
    assert 'tier = "power"' in content
    assert 'monthly_credits = 10000' in content
    assert 'cycle_start = 2026-06-15' in content or 'cycle_start = "2026-06-15"' in content
```

- [ ] **Step 3: Rodar — falha**

```bash
pytest tests/test_config.py -v
```

Expected: ImportError em `kiro_dash.config`.

- [ ] **Step 4: Implementar `config.py`**

Criar `src/kiro_dash/config.py`:

```python
"""Configuração persistente do kiro-dash em ``~/.config/kiro-dash/config.toml``.

Atualmente armazena apenas o plano declarado (tier + créditos mensais +
data de início do ciclo de billing). Pode crescer pra outras prefs
no futuro sem quebrar este schema.
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import tomli_w

VALID_TIERS = {"free", "pro", "pro+", "power", "enterprise"}

DEFAULT_MONTHLY_CREDITS: dict[str, int] = {
    "free": 50,
    "pro": 1000,
    "pro+": 2000,
    "power": 10000,
    "enterprise": 99_999_999,  # sem cap real
}


@dataclass(frozen=True, slots=True)
class PlanConfig:
    """Plano declarado pelo usuário."""

    tier: str  # one of VALID_TIERS
    monthly_credits: int
    cycle_start: date


def default_config_path() -> Path:
    """``$XDG_CONFIG_HOME/kiro-dash/config.toml`` ou ``~/.config/kiro-dash/config.toml``."""
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / "kiro-dash" / "config.toml"


def _today_first() -> date:
    return date.today().replace(day=1)


def load_plan(path: Path | None = None) -> PlanConfig:
    """Carrega o plano do TOML.

    Faltando o arquivo, devolve plano default ``free``. Faltando campos
    individuais, preenche com defaults coerentes. Tier inválido cai para
    ``free``.
    """
    if path is None:
        path = default_config_path()

    if not path.is_file():
        return PlanConfig(tier="free", monthly_credits=50, cycle_start=_today_first())

    try:
        with path.open("rb") as f:
            raw = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return PlanConfig(tier="free", monthly_credits=50, cycle_start=_today_first())

    plan_data = raw.get("plan", {}) if isinstance(raw, dict) else {}
    tier = str(plan_data.get("tier", "free")).strip().lower()
    if tier not in VALID_TIERS:
        tier = "free"

    monthly_credits = plan_data.get("monthly_credits")
    if not isinstance(monthly_credits, int) or monthly_credits <= 0:
        monthly_credits = DEFAULT_MONTHLY_CREDITS[tier]

    cycle_raw = plan_data.get("cycle_start")
    if isinstance(cycle_raw, date):
        cycle_start = cycle_raw
    elif isinstance(cycle_raw, str):
        try:
            cycle_start = date.fromisoformat(cycle_raw)
        except ValueError:
            cycle_start = _today_first()
    else:
        cycle_start = _today_first()

    return PlanConfig(tier=tier, monthly_credits=monthly_credits, cycle_start=cycle_start)


def save_plan(plan: PlanConfig, path: Path | None = None) -> None:
    """Persiste o plano em TOML, criando diretórios pais se necessário."""
    if path is None:
        path = default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "plan": {
            "tier": plan.tier,
            "monthly_credits": plan.monthly_credits,
            "cycle_start": plan.cycle_start,  # tomli_w serializa datetime.date nativamente
        }
    }
    with path.open("wb") as f:
        tomli_w.dump(data, f)
```

- [ ] **Step 5: Rodar — passa**

```bash
pytest tests/test_config.py -v
```

Expected: 8 PASSED.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/kiro_dash/config.py tests/test_config.py
git commit -m "feat(config): TOML em XDG_CONFIG_HOME com defaults por tier"
```

---

### Task 2: Cálculo de saldo no aggregator

**Files:**
- Modify: `src/kiro_dash/aggregator.py`
- Create: `tests/test_balance.py`

- [ ] **Step 1: Escrever testes**

Criar `tests/test_balance.py`:

```python
"""Testes da função de saldo de ciclo."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from kiro_dash.aggregator import balance_in_cycle, turns_in_cycle
from tests.fixtures.sessions_synthetic import make_session, make_turn


def test_turns_in_cycle_includes_only_after_cycle_start():
    cycle_start = date(2026, 5, 1)
    s = make_session(turns=[
        make_turn(end_timestamp=datetime(2026, 4, 30, 23, 59, tzinfo=timezone.utc), credits=1.0),
        make_turn(end_timestamp=datetime(2026, 5, 1, 0, 1, tzinfo=timezone.utc), credits=2.0),
        make_turn(end_timestamp=datetime(2026, 5, 15, tzinfo=timezone.utc), credits=3.0),
    ])
    pairs = turns_in_cycle([s], cycle_start)
    creds = sorted(t.credits for _, t in pairs)
    assert creds == [2.0, 3.0]


def test_balance_in_cycle_calculates_consumed_and_remaining():
    cycle_start = date.today().replace(day=1)
    now = datetime.now(timezone.utc)
    s = make_session(turns=[
        make_turn(end_timestamp=now - timedelta(days=1), credits=300.0),
        make_turn(end_timestamp=now, credits=200.0),
    ])
    bal = balance_in_cycle([s], cycle_start, monthly_credits=1000)
    assert bal["consumed"] == 500.0
    assert bal["remaining"] == 500.0
    assert bal["pct_used"] == 50.0
    assert bal["monthly_credits"] == 1000
    assert bal["cycle_start"] == cycle_start


def test_balance_in_cycle_caps_pct_at_100_when_overage():
    cycle_start = date.today().replace(day=1)
    s = make_session(turns=[make_turn(
        end_timestamp=datetime.now(timezone.utc), credits=1500.0,
    )])
    bal = balance_in_cycle([s], cycle_start, monthly_credits=1000)
    assert bal["consumed"] == 1500.0
    assert bal["remaining"] == -500.0  # negativo, indica overage
    assert bal["pct_used"] == 150.0  # não cap; UI mostra >100% em vermelho
```

- [ ] **Step 2: Rodar — falha**

```bash
pytest tests/test_balance.py -v
```

Expected: ImportError em `balance_in_cycle`/`turns_in_cycle`.

- [ ] **Step 3: Implementar**

Em `src/kiro_dash/aggregator.py`, adicionar após `turns_in_last_days`:

```python
def turns_in_cycle(
    sessions: list[Session],
    cycle_start: date,
) -> list[tuple[Session, Turn]]:
    """Pares (sessão, turn) com end_timestamp >= cycle_start (UTC).

    A conversão da ``date`` local para UTC usa o fuso do sistema; o
    instante ``cycle_start 00:00 local`` é o pivô.
    """
    tz_local = datetime.now().astimezone().tzinfo
    start_local = datetime.combine(cycle_start, datetime.min.time(), tzinfo=tz_local)
    start_utc = start_local.astimezone(timezone.utc)

    out: list[tuple[Session, Turn]] = []
    for s in sessions:
        for t in s.turns:
            if t.end_timestamp >= start_utc:
                out.append((s, t))
    return out


def balance_in_cycle(
    sessions: list[Session],
    cycle_start: date,
    *,
    monthly_credits: int,
) -> dict:
    """Calcula saldo do ciclo: consumed / remaining / pct_used."""
    pairs = turns_in_cycle(sessions, cycle_start)
    consumed = sum(t.credits for _, t in pairs)
    remaining = monthly_credits - consumed
    pct = (consumed / monthly_credits * 100.0) if monthly_credits > 0 else 0.0
    return {
        "consumed": round(consumed, 6),
        "remaining": round(remaining, 6),
        "pct_used": round(pct, 2),
        "monthly_credits": monthly_credits,
        "cycle_start": cycle_start,
        "turns": len(pairs),
        "sessions": len({s.session_id for s, _ in pairs}),
    }
```

- [ ] **Step 4: Rodar — passa**

```bash
pytest tests/test_balance.py -v
```

Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/kiro_dash/aggregator.py tests/test_balance.py
git commit -m "feat(aggregator): turns_in_cycle + balance_in_cycle"
```

---

### Task 3: Subcomandos `plan get/set` + `balance`

**Files:**
- Modify: `src/kiro_dash/cli.py`
- Create: `tests/test_plan_command.py`

- [ ] **Step 1: Escrever testes do CLI**

Criar `tests/test_plan_command.py`:

```python
"""Smoke dos subcomandos plan e balance."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from kiro_dash.cli import main
from kiro_dash.config import PlanConfig
from tests.fixtures.sessions_synthetic import make_session, make_turn


def test_plan_get_shows_current_plan(tmp_path):
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text('[plan]\ntier = "pro+"\nmonthly_credits = 2000\ncycle_start = 2026-05-01\n')
    with patch("kiro_dash.cli.default_config_path", return_value=cfg_path):
        runner = CliRunner()
        result = runner.invoke(main, ["plan", "get"])
    assert result.exit_code == 0
    assert "pro+" in result.output
    assert "2000" in result.output
    assert "2026-05-01" in result.output


def test_plan_set_persists_tier(tmp_path):
    cfg_path = tmp_path / "config.toml"
    with patch("kiro_dash.cli.default_config_path", return_value=cfg_path):
        runner = CliRunner()
        result = runner.invoke(main, ["plan", "set", "pro+"])
    assert result.exit_code == 0
    content = cfg_path.read_text()
    assert 'tier = "pro+"' in content
    assert 'monthly_credits = 2000' in content


def test_plan_set_invalid_tier_rejects(tmp_path):
    cfg_path = tmp_path / "config.toml"
    with patch("kiro_dash.cli.default_config_path", return_value=cfg_path):
        runner = CliRunner()
        result = runner.invoke(main, ["plan", "set", "wrong-tier"])
    assert result.exit_code != 0
    assert "tier" in result.output.lower()


def test_plan_set_with_credits_override(tmp_path):
    cfg_path = tmp_path / "config.toml"
    with patch("kiro_dash.cli.default_config_path", return_value=cfg_path):
        runner = CliRunner()
        result = runner.invoke(main, [
            "plan", "set", "pro", "--credits", "1500", "--cycle-start", "2026-04-15"
        ])
    assert result.exit_code == 0
    content = cfg_path.read_text()
    assert 'monthly_credits = 1500' in content
    assert '2026-04-15' in content


def _fake_sessions_with_credits(total_credits: float):
    now = datetime.now(timezone.utc)
    return [make_session(turns=[
        make_turn(end_timestamp=now - timedelta(hours=1), credits=total_credits),
    ])]


def test_balance_shows_consumption_below_threshold(tmp_path):
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        f'[plan]\ntier = "pro+"\nmonthly_credits = 2000\n'
        f'cycle_start = {date.today().replace(day=1).isoformat()}\n'
    )
    with patch("kiro_dash.cli.default_config_path", return_value=cfg_path), \
         patch("kiro_dash.cli.load_all_sessions", return_value=_fake_sessions_with_credits(500.0)):
        runner = CliRunner()
        result = runner.invoke(main, ["balance"])
    assert result.exit_code == 0
    assert "500" in result.output
    assert "1500" in result.output  # remaining
    assert "25" in result.output    # pct


def test_balance_warns_when_above_80_pct(tmp_path):
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        f'[plan]\ntier = "pro"\nmonthly_credits = 1000\n'
        f'cycle_start = {date.today().replace(day=1).isoformat()}\n'
    )
    with patch("kiro_dash.cli.default_config_path", return_value=cfg_path), \
         patch("kiro_dash.cli.load_all_sessions", return_value=_fake_sessions_with_credits(850.0)):
        runner = CliRunner()
        result = runner.invoke(main, ["balance"])
    assert result.exit_code == 0
    # Tem que ter algum indicador visual de alerta — testamos pelo nome cru,
    # já que o Rich exporta ANSI; o teste é pelo número >= 80
    assert "85" in result.output  # pct
```

- [ ] **Step 2: Rodar — falha**

```bash
pytest tests/test_plan_command.py -v
```

Expected: FAIL `Error: No such command 'plan'` / `'balance'`.

- [ ] **Step 3: Implementar comandos**

Em `src/kiro_dash/cli.py`, adicionar imports:

```python
from kiro_dash.aggregator import balance_in_cycle, turns_in_cycle
from kiro_dash.config import (
    DEFAULT_MONTHLY_CREDITS,
    VALID_TIERS,
    PlanConfig,
    default_config_path,
    load_plan,
    save_plan,
)
```

E adicionar grupo + comandos antes do `if __name__ == "__main__"`:

```python
# ─── plan ─────────────────────────────────────────────────────────────────


@main.group()
def plan() -> None:
    """Gestão do plano declarado (tier, créditos mensais, ciclo)."""


@plan.command("get")
def plan_get() -> None:
    """Mostra o plano atual."""
    p = load_plan(default_config_path())
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(style="dim")
    table.add_column()
    table.add_row("Tier", p.tier)
    table.add_row("Créditos mensais", str(p.monthly_credits))
    table.add_row("Ciclo iniciado", p.cycle_start.isoformat())
    table.add_row("Config", str(default_config_path()))
    console.print(Panel(table, title="Plano", expand=False))


@plan.command("set")
@click.argument("tier")
@click.option("--credits", "credits_override", type=int, default=None,
              help="Override do default de créditos da tier.")
@click.option("--cycle-start", "cycle_start_str", default=None,
              help="Data de início do ciclo (YYYY-MM-DD).")
def plan_set(tier: str, credits_override: int | None, cycle_start_str: str | None) -> None:
    """Define o plano. Tier deve estar em {free, pro, pro+, power, enterprise}."""
    if tier not in VALID_TIERS:
        console.print(f"[red]tier inválido: '{tier}'. Use um de: {sorted(VALID_TIERS)}.[/red]")
        raise SystemExit(2)

    monthly = credits_override or DEFAULT_MONTHLY_CREDITS[tier]

    if cycle_start_str:
        from datetime import date as _date
        try:
            cycle = _date.fromisoformat(cycle_start_str)
        except ValueError:
            console.print(f"[red]cycle-start inválido: '{cycle_start_str}'. Use YYYY-MM-DD.[/red]")
            raise SystemExit(2)
    else:
        existing = load_plan(default_config_path())
        cycle = existing.cycle_start

    p = PlanConfig(tier=tier, monthly_credits=monthly, cycle_start=cycle)
    save_plan(p, default_config_path())
    console.print(f"[green]Plano salvo:[/green] {p.tier} ({p.monthly_credits} cr/mês), ciclo {p.cycle_start.isoformat()}")


# ─── balance ──────────────────────────────────────────────────────────────


def _balance_color(pct: float) -> str:
    if pct >= 95:
        return "red"
    if pct >= 80:
        return "yellow"
    return "green"


@main.command()
def balance() -> None:
    """Saldo estimado do ciclo corrente."""
    p = load_plan(default_config_path())
    sessions = load_all_sessions()
    bal = balance_in_cycle(sessions, p.cycle_start, monthly_credits=p.monthly_credits)

    color = _balance_color(bal["pct_used"])
    bar = Text()
    used_blocks = min(20, int(bal["pct_used"] / 5))
    bar.append("█" * used_blocks, style=color)
    bar.append("░" * (20 - used_blocks), style="dim")

    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(style="dim")
    table.add_column()
    table.add_row("Tier", p.tier)
    table.add_row("Ciclo desde", p.cycle_start.isoformat())
    table.add_row(
        "Consumo",
        f"{_fmt_credits(bal['consumed'])} / {bal['monthly_credits']} créditos",
    )
    table.add_row("Restante", _fmt_credits(bal["remaining"]))
    table.add_row("Uso", Text(f"{bal['pct_used']:.1f}%", style=color))
    table.add_row("Barra", bar)
    table.add_row("Turns no ciclo", str(bal["turns"]))
    table.add_row("Sessões no ciclo", str(bal["sessions"]))

    title = "Saldo do ciclo"
    if bal["pct_used"] >= 95:
        title += " — ⚠️ próximo do limite"
    elif bal["pct_used"] >= 80:
        title += " — atenção"

    console.print(Panel(table, title=title, expand=False))
```

- [ ] **Step 4: Rodar — passa**

```bash
pytest tests/test_plan_command.py -v
```

Expected: 6 PASSED.

- [ ] **Step 5: Smoke manual**

```bash
kiro-dash plan get
kiro-dash plan set pro+
kiro-dash balance
```

Expected: `plan get` mostra plano default no início; `plan set` persiste; `balance` mostra consumo do ciclo com barra colorida.

- [ ] **Step 6: Commit**

```bash
git add src/kiro_dash/cli.py tests/test_plan_command.py
git commit -m "feat(cli): plan get/set + balance com barra colorida e alertas"
```

---

### Task 4: Integração no `today` (header com alerta)

**Files:**
- Modify: `src/kiro_dash/cli.py`

- [ ] **Step 1: Modificar comando `today` para mostrar contexto do plano**

Localize a função `today` em `cli.py` e adicione, logo após o panel "Hoje":

```python
# Após `console.print(Panel(header, title="Hoje", expand=False))` adicionar:

p = load_plan(default_config_path())
bal = balance_in_cycle(sessions, p.cycle_start, monthly_credits=p.monthly_credits)
ctx_color = _balance_color(bal["pct_used"])
ctx = Text()
ctx.append(f"  Ciclo {p.tier}: ", style="dim")
ctx.append(f"{_fmt_credits(bal['consumed'])} / {bal['monthly_credits']} ", style=ctx_color)
ctx.append(f"({bal['pct_used']:.1f}%)", style=ctx_color)
console.print(ctx)
console.print()
```

- [ ] **Step 2: Smoke manual**

```bash
kiro-dash today
```

Expected: depois do panel "Hoje" aparece linha tipo `Ciclo pro+: 850 / 2000 (42.5%)` colorida conforme threshold.

- [ ] **Step 3: Commit**

```bash
git add src/kiro_dash/cli.py
git commit -m "feat(today): linha de contexto do ciclo com alerta visual"
```

---

### Task 5: README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Adicionar seção**

Antes da Licença:

```markdown
## Plano e saldo estimado

Declare seu plano para que o painel mostre saldo restante do ciclo:

```bash
kiro-dash plan set pro+              # 2000 créditos/mês (default da tier)
kiro-dash plan set pro --credits 1500 --cycle-start 2026-05-15  # overrides
kiro-dash plan get
kiro-dash balance                    # painel dedicado
kiro-dash today                      # mostra linha de contexto do ciclo
```

Tiers reconhecidas: `free` (50), `pro` (1000), `pro+` (2000), `power`
(10000), `enterprise` (sem cap real).

Alertas visuais: amarelo a partir de 80%, vermelho a partir de 95%.

Config persiste em `~/.config/kiro-dash/config.toml`.

> **Nota:** o saldo é estimativa local — se você usa Kiro em mais de um
> dispositivo sem o `kiro-dash sync` ativo, o consumo real pode ser maior
> que o calculado aqui. Dashboard web (`kiro-cli dashboard`) é a fonte
> autoritativa.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs(plan): instruções de plan + balance + alertas"
```

---

## Self-Review Checklist

- [ ] Tiers: `free`, `pro`, `pro+`, `power`, `enterprise` — todas com defaults
- [ ] TOML round-trip preservando data, int, string
- [ ] `cycle_start` aceito como `date` nativo OU string ISO
- [ ] Tier inválido salvo no arquivo cai pra `free` no load (defensivo)
- [ ] Alerta amarelo >=80%, vermelho >=95%
- [ ] `today` mostra linha de contexto do ciclo
- [ ] Override de créditos via `--credits` funciona
- [ ] Override de ciclo via `--cycle-start YYYY-MM-DD` funciona
- [ ] README documenta tiers e thresholds

## Done When

- `pytest tests/test_config.py tests/test_balance.py tests/test_plan_command.py -v` → 17 PASSED
- `kiro-dash plan set pro+` + `kiro-dash balance` mostram dados corretos
- `kiro-dash today` mostra linha do ciclo
- 5 commits no branch `feat/wave2-plan-balance`
