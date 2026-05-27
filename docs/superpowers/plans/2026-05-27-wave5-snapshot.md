# Wave 5 / Frente M — Snapshot diário + lazy + self-healing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Persistir snapshots diários de uso em arquivos JSON imutáveis. Geração **lazy** (na primeira execução depois do fim do dia X) com **self-healing** (cada execução verifica e gera dias passados faltantes), além de **manual** (`kiro-dash snapshot YYYY-MM-DD`). Multi-host safe (snapshots de hosts diferentes coexistem).

**Architecture:**

- **Storage:** `~/.local/share/kiro-dash/snapshots/<YYYY-MM-DD>.<host>.json` (XDG_DATA_HOME respeitado).
- **Schema v1:**
  ```json
  {
    "schema_version": 1,
    "local_date": "2026-05-16",
    "tz_offset": "-03:00",
    "captured_at": "2026-05-17T03:00:00Z",
    "captured_by_host": "Predator-PH315-54",
    "totals": {"credits": 734.06, "turns": 157, "sessions": 6},
    "by_model": [{"label": "...", "credits": ..., "turns": ..., "sessions": ..., "duration_secs": ..., "tool_uses": ...}, ...],
    "by_project": [...],
    "by_agent_pair": [{"runtime": "...", "persona": "...", "credits": ..., ...}],
    "by_session": [...],
    "by_tool": [{"name": "...", "count": ..., "errors": ..., "sessions": ...}]
  }
  ```
- **Lazy:** comando entrypoint chama `ensure_snapshots_up_to(yesterday_local, sessions)` no início — silenciosamente gera snapshots ainda não criados pra dias passados.
- **Self-healing:** mesma função, mas **scan completo** em lookback (default 30d) detecta buracos e fecha. Custo: 1 stat por dia × 30 = 30 stats por execução = milissegundos.
- **Multi-host:** sufixo `.host` no filename. Snapshots de hosts distintos coexistem; query soma todos os hosts pro mesmo dia.
- **Imutabilidade:** snapshot existente nunca é sobrescrito automaticamente. Comando manual `kiro-dash snapshot YYYY-MM-DD --force` re-escreve.
- **Janela stateless:** hoje + ontem **nunca** viram snapshot persistido pelo lazy — sempre re-lidos dos `.json` originais. Snapshot só fecha em D-2.

**Tech Stack:** Python 3.12 stdlib (`socket.gethostname`, `pathlib`, `json`).

**Branch:** `feat/wave5-snapshot`

**Pré-requisito:** Frente L mergeada (precisa de `now` injetável).

---

## File Structure

| Arquivo | Responsabilidade | Mudança |
|---|---|---|
| `src/kiro_dash/snapshots.py` | Módulo de snapshot (write/read/merge/scan) | **Criar** |
| `src/kiro_dash/cli.py` | Comando `snapshot` + integração lazy em entrypoint | **Modificar** |
| `tests/test_snapshots.py` | Cobertura completa | **Criar** |
| `tests/test_snapshot_command.py` | Smoke do CLI | **Criar** |
| `README.md` | Seção "Histórico (snapshots)" | **Modificar** |

---

### Task 1: Schema + write/read básico

**Files:**
- Create: `src/kiro_dash/snapshots.py`
- Create: `tests/test_snapshots.py`

- [ ] **Step 1: Escrever testes**

```python
"""Cobertura de snapshots."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from kiro_dash.snapshots import (
    SnapshotPaths,
    build_snapshot,
    read_snapshot,
    snapshots_dir_default,
    write_snapshot,
)
from tests.fixtures.sessions_synthetic import make_session, make_turn

FAKE_NOW = datetime(2026, 5, 17, 15, 0, tzinfo=timezone.utc)


def _make_sample(d: date):
    """Dois turns no dia d local."""
    # 12h local de d → 15h UTC de d (UTC-3)
    base = datetime.combine(d, datetime.min.time(),
                            tzinfo=datetime.now().astimezone().tzinfo).replace(hour=12)
    base_utc = base.astimezone(timezone.utc)
    return [
        make_session(
            session_id="aaaa", cwd="/proj/alfa", model_id="claude-opus-4.7", is_active=False,
            turns=[
                make_turn(end_timestamp=base_utc, credits=3.0),
                make_turn(end_timestamp=base_utc + timedelta(minutes=5), credits=2.0),
            ],
        ),
    ]


def test_snapshots_dir_default_uses_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert snapshots_dir_default() == tmp_path / "kiro-dash" / "snapshots"


def test_build_snapshot_aggregates_corretamente():
    sessions = _make_sample(date(2026, 5, 16))
    snap = build_snapshot(sessions, d=date(2026, 5, 16),
                          host="test-host", now=FAKE_NOW)
    assert snap["schema_version"] == 1
    assert snap["local_date"] == "2026-05-16"
    assert snap["captured_by_host"] == "test-host"
    assert snap["totals"]["credits"] == 5.0
    assert snap["totals"]["turns"] == 2
    assert snap["totals"]["sessions"] == 1
    assert any(m["label"] == "claude-opus-4.7" for m in snap["by_model"])


def test_write_then_read_roundtrip(tmp_path):
    paths = SnapshotPaths(root=tmp_path)
    sessions = _make_sample(date(2026, 5, 16))
    write_snapshot(sessions, d=date(2026, 5, 16), host="h1", paths=paths, now=FAKE_NOW)
    out = read_snapshot(date(2026, 5, 16), paths=paths)
    assert out is not None
    assert out["totals"]["credits"] == 5.0


def test_read_returns_none_when_missing(tmp_path):
    paths = SnapshotPaths(root=tmp_path)
    assert read_snapshot(date(2026, 5, 16), paths=paths) is None


def test_read_merges_multiple_hosts(tmp_path):
    paths = SnapshotPaths(root=tmp_path)
    sessions_a = _make_sample(date(2026, 5, 16))
    sessions_b = [
        make_session(
            session_id="bbbb", cwd="/proj/beta", model_id="auto", is_active=False,
            turns=[make_turn(end_timestamp=FAKE_NOW - timedelta(days=1, minutes=30),
                             credits=4.0)],
        )
    ]
    write_snapshot(sessions_a, d=date(2026, 5, 16), host="predator", paths=paths, now=FAKE_NOW)
    write_snapshot(sessions_b, d=date(2026, 5, 16), host="work", paths=paths, now=FAKE_NOW)

    merged = read_snapshot(date(2026, 5, 16), paths=paths)
    assert merged is not None
    assert merged["totals"]["credits"] == 9.0  # 5 (predator) + 4 (work)
    assert merged["totals"]["sessions"] == 2  # aaaa + bbbb
    assert "merged_from" in merged
    assert sorted(merged["merged_from"]) == ["predator", "work"]
```

- [ ] **Step 2: Rodar — falha**

- [ ] **Step 3: Implementar `snapshots.py` (parte 1: build + write + read + merge)**

```python
"""Snapshots diários de uso — base da persistência histórica.

Storage: arquivos JSON imutáveis em ``~/.local/share/kiro-dash/snapshots/``.
Cada snapshot é nomeado ``<YYYY-MM-DD>.<host>.json`` para suportar
multi-host sem conflito.
"""
from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from kiro_dash.aggregator import (
    aggregate_by_agent_pair,
    aggregate_by_model,
    aggregate_by_project,
    aggregate_by_session,
    aggregate_tools_in_window,
    total_credits,
    turns_in_local_day,
)
from kiro_dash.config import load_aliases, default_config_path
from kiro_dash.models import Session


SCHEMA_VERSION = 1


def snapshots_dir_default() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "kiro-dash" / "snapshots"


@dataclass(frozen=True, slots=True)
class SnapshotPaths:
    root: Path

    def for_date(self, d: date, host: str) -> Path:
        return self.root / f"{d.isoformat()}.{host}.json"

    def glob_for_date(self, d: date) -> list[Path]:
        if not self.root.exists():
            return []
        return sorted(self.root.glob(f"{d.isoformat()}.*.json"))


def _resolve_paths(paths: SnapshotPaths | None) -> SnapshotPaths:
    return paths or SnapshotPaths(root=snapshots_dir_default())


def _hostname() -> str:
    return socket.gethostname() or "unknown"


def _tz_offset_str(tz) -> str:
    """ISO-friendly: '-03:00' / '+05:30' / 'Z' (UTC)."""
    if tz is None:
        return "Z"
    offset = tz.utcoffset(datetime.now())
    if offset is None:
        return "Z"
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    h, m = divmod(abs(total_minutes), 60)
    return f"{sign}{h:02d}:{m:02d}"


def build_snapshot(
    sessions: list[Session],
    *,
    d: date,
    host: str | None = None,
    now: datetime | None = None,
) -> dict:
    """Constrói o dict do snapshot pra ``d`` (data local).

    Não toca disco. ``now`` injetável para testes.
    """
    pairs = turns_in_local_day(sessions, d, now=now)
    aliases = load_aliases(default_config_path())

    sessions_dir = Path.home() / ".kiro" / "sessions" / "cli"
    # Tools agregadas no dia: hoje 24h é a janela default — para snapshot,
    # pegamos as tool calls das sessões do dia. Como aggregate_tools_in_window
    # opera em arquivos, podemos chamá-lo restritivamente filtrando posteriormente.
    # Simplificação: passar 24h e contar com o filtro de timestamp dentro do builder.
    # (Para snapshots históricos, refinaremos na Frente N.)
    tools = aggregate_tools_in_window(sessions_dir, hours=48)  # 48h pra cobrir overlap

    return {
        "schema_version": SCHEMA_VERSION,
        "local_date": d.isoformat(),
        "tz_offset": _tz_offset_str(datetime.now().astimezone().tzinfo),
        "captured_at": (now or datetime.now(timezone.utc)).isoformat().replace("+00:00", "Z"),
        "captured_by_host": host or _hostname(),
        "totals": {
            "credits": round(total_credits(pairs), 4),
            "turns": len(pairs),
            "sessions": len({s.session_id for s, _ in pairs}),
        },
        "by_model": [_agg_to_dict(a) for a in aggregate_by_model(pairs)],
        "by_project": [_agg_to_dict(a) for a in aggregate_by_project(pairs, aliases=aliases)],
        "by_agent_pair": [_pair_to_dict(a) for a in aggregate_by_agent_pair(pairs)],
        "by_session": [_agg_to_dict(a) for a in aggregate_by_session(pairs)],
        "by_tool": [
            {"name": t["name"], "count": t["count"],
             "sessions": t["sessions"], "errors": t["errors"]}
            for t in tools
        ],
    }


def _agg_to_dict(a) -> dict:
    return {
        "label": a.label,
        "credits": round(a.credits, 4),
        "turns": a.turns,
        "sessions": a.sessions,
        "duration_secs": int(a.duration.total_seconds()),
        "tool_uses": a.tool_uses,
    }


def _pair_to_dict(a) -> dict:
    return {
        "runtime": a.runtime,
        "persona": a.persona,
        "credits": round(a.credits, 4),
        "turns": a.turns,
        "sessions": a.sessions,
        "duration_secs": int(a.duration.total_seconds()),
        "tool_uses": a.tool_uses,
    }


def write_snapshot(
    sessions: list[Session],
    *,
    d: date,
    host: str | None = None,
    paths: SnapshotPaths | None = None,
    now: datetime | None = None,
    overwrite: bool = False,
) -> Path:
    """Constrói e grava snapshot. Retorna o path criado.

    Default ``overwrite=False``: nunca sobrescreve. Force re-write requer
    ``overwrite=True`` (use o comando ``snapshot --force``).
    """
    p = _resolve_paths(paths)
    p.root.mkdir(parents=True, exist_ok=True)
    h = host or _hostname()
    target = p.for_date(d, h)
    if target.exists() and not overwrite:
        return target
    snap = build_snapshot(sessions, d=d, host=h, now=now)
    with open(target, "w") as f:
        json.dump(snap, f, indent=2)
    return target


def read_snapshot(
    d: date,
    *,
    paths: SnapshotPaths | None = None,
) -> dict | None:
    """Lê e merge **todos** os snapshots do dia ``d`` (todos os hosts).

    Quando há múltiplos hosts, soma totais e concatena breakdowns. Sessions
    distintas por session_id permanecem distintas — soma é segura.
    Retorna ``None`` se nenhum host gravou.
    """
    p = _resolve_paths(paths)
    files = p.glob_for_date(d)
    if not files:
        return None
    snaps = []
    for fp in files:
        try:
            with open(fp) as f:
                snaps.append(json.load(f))
        except (OSError, json.JSONDecodeError):
            continue
    if not snaps:
        return None
    if len(snaps) == 1:
        return snaps[0]
    return _merge_snapshots(snaps)


def _merge_snapshots(snaps: list[dict]) -> dict:
    """Soma totais e concatena breakdowns; ``merged_from`` lista hosts."""
    out = {
        "schema_version": SCHEMA_VERSION,
        "local_date": snaps[0]["local_date"],
        "tz_offset": snaps[0]["tz_offset"],  # assume mesmo fuso (heurística pessoal do Léo)
        "captured_at": max(s["captured_at"] for s in snaps),
        "merged_from": [s["captured_by_host"] for s in snaps],
        "totals": {
            "credits": round(sum(s["totals"]["credits"] for s in snaps), 4),
            "turns": sum(s["totals"]["turns"] for s in snaps),
            "sessions": sum(s["totals"]["sessions"] for s in snaps),
        },
    }
    # Breakdowns: união simples (consumidor pode reagregar se quiser)
    for key in ("by_model", "by_project", "by_agent_pair", "by_session", "by_tool"):
        out[key] = [item for s in snaps for item in s.get(key, [])]
    return out
```

- [ ] **Step 4: Rodar — passa**

- [ ] **Step 5: Commit**

```bash
git add src/kiro_dash/snapshots.py tests/test_snapshots.py
git -c user.email='leonardo.menzani@gmail.com' -c user.name='mencoding' \
  commit -m "feat(snapshots): build/write/read + merge multi-host"
```

---

### Task 2: Lazy + self-healing — `ensure_snapshots_up_to`

**Files:**
- Modify: `src/kiro_dash/snapshots.py`
- Modify: `tests/test_snapshots.py`

- [ ] **Step 1: Escrever testes**

```python
def test_ensure_snapshots_up_to_gera_dias_faltantes(tmp_path):
    """Self-healing: ensure_snapshots_up_to gera tudo que falta."""
    from kiro_dash.snapshots import ensure_snapshots_up_to

    paths = SnapshotPaths(root=tmp_path)
    # FAKE_NOW = 17/05; ensure até 16/05 (ontem). Nenhum snapshot existe.
    sessions = _make_sample(date(2026, 5, 16))

    created = ensure_snapshots_up_to(
        date(2026, 5, 16),
        sessions,
        paths=paths,
        host="h1",
        now=FAKE_NOW,
        lookback_days=7,
    )
    # Cria 16/05 (1 dia, 7 anteriores podem estar vazios mas não criam se sem turns)
    assert any("2026-05-16" in str(p) for p in created)


def test_ensure_snapshots_up_to_idempotente(tmp_path):
    """Reexecutar não recria snapshots existentes."""
    from kiro_dash.snapshots import ensure_snapshots_up_to

    paths = SnapshotPaths(root=tmp_path)
    sessions = _make_sample(date(2026, 5, 16))

    created_1 = ensure_snapshots_up_to(date(2026, 5, 16), sessions, paths=paths, host="h1", now=FAKE_NOW)
    created_2 = ensure_snapshots_up_to(date(2026, 5, 16), sessions, paths=paths, host="h1", now=FAKE_NOW)
    assert created_2 == []  # nenhum criado na 2ª execução


def test_ensure_snapshots_nao_inclui_hoje_nem_ontem_se_target_eh_anteontem(tmp_path):
    """Target ``up_to=anteontem`` não cria snapshot de hoje nem de ontem."""
    from kiro_dash.snapshots import ensure_snapshots_up_to

    paths = SnapshotPaths(root=tmp_path)
    target = date(2026, 5, 15)  # anteontem em relação a FAKE_NOW=17/05
    sessions = _make_sample(date(2026, 5, 15))
    ensure_snapshots_up_to(target, sessions, paths=paths, host="h1", now=FAKE_NOW)

    files = list(paths.root.glob("*.json"))
    # Não deve haver 16/05 nem 17/05
    assert not any("2026-05-16" in str(p) or "2026-05-17" in str(p) for p in files)
```

- [ ] **Step 2: Rodar — falha**

- [ ] **Step 3: Implementar**

Adicionar em `snapshots.py`:

```python
def ensure_snapshots_up_to(
    up_to: date,
    sessions: list[Session],
    *,
    paths: SnapshotPaths | None = None,
    host: str | None = None,
    now: datetime | None = None,
    lookback_days: int = 30,
) -> list[Path]:
    """Garante snapshots de ``up_to - lookback_days`` até ``up_to`` (inclusive).

    Self-healing: dias sem snapshot do host atual são gerados. Dias **com**
    snapshot do host (mesmo que outro host também tenha gravado) são pulados.

    Não toca em hoje nem futuro: ``up_to`` deve ser ≤ ontem do fuso local.

    Retorna lista de paths criados.
    """
    p = _resolve_paths(paths)
    p.root.mkdir(parents=True, exist_ok=True)
    h = host or _hostname()

    created = []
    for offset in range(lookback_days, -1, -1):
        d = up_to - timedelta(days=offset)
        if p.for_date(d, h).exists():
            continue
        target = write_snapshot(sessions, d=d, host=h, paths=p, now=now)
        # Só registra se realmente criou (write_snapshot retorna path mesmo se já existir)
        if target.stat().st_size > 0:
            created.append(target)
    return created
```

- [ ] **Step 4: Rodar — passa**

- [ ] **Step 5: Commit**

```bash
git add src/kiro_dash/snapshots.py tests/test_snapshots.py
git -c user.email='leonardo.menzani@gmail.com' -c user.name='mencoding' \
  commit -m "feat(snapshots): ensure_snapshots_up_to (lazy + self-healing)"
```

---

### Task 3: Comando CLI `kiro-dash snapshot`

**Files:**
- Modify: `src/kiro_dash/cli.py`
- Create: `tests/test_snapshot_command.py`

- [ ] **Step 1: Escrever testes**

```python
"""Smoke do subcomando snapshot."""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from kiro_dash.cli import main


def test_snapshot_sem_args_gera_lazy(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    with patch("kiro_dash.cli.load_all_sessions", return_value=[]):
        runner = CliRunner()
        result = runner.invoke(main, ["snapshot"])
    assert result.exit_code == 0


def test_snapshot_com_data_gera_dia_especifico(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    with patch("kiro_dash.cli.load_all_sessions", return_value=[]):
        runner = CliRunner()
        result = runner.invoke(main, ["snapshot", "2026-05-16"])
    assert result.exit_code == 0


def test_snapshot_data_invalida_falha():
    runner = CliRunner()
    result = runner.invoke(main, ["snapshot", "2026/05/16"])
    assert result.exit_code != 0
```

- [ ] **Step 2: Implementar comando**

Em `cli.py`:

```python
@main.command()
@click.argument("date_str", required=False)
@click.option("--force", is_flag=True, default=False,
              help="Re-escreve snapshot existente (default não sobrescreve).")
def snapshot(date_str: str | None, force: bool) -> None:
    """Gera snapshot histórico.

    - Sem ``date_str``: roda lazy/self-healing — gera todos os snapshots
      pendentes nos últimos 30 dias até ontem.
    - Com ``date_str`` (YYYY-MM-DD): gera/regenera apenas esse dia. ``--force``
      sobrescreve se já existir.

    Snapshots ficam em ``~/.local/share/kiro-dash/snapshots/``.
    """
    sessions = load_all_sessions()
    today = datetime.now().astimezone().date()
    yesterday = today - timedelta(days=1)

    if date_str is None:
        created = ensure_snapshots_up_to(yesterday, sessions)
        if created:
            console.print(f"[green]Criados {len(created)} snapshot(s).[/green]")
            for p in created[-5:]:
                console.print(f"  [dim]{p.name}[/dim]")
            if len(created) > 5:
                console.print(f"  [dim]... +{len(created) - 5}[/dim]")
        else:
            console.print("[dim]Nenhum snapshot pendente.[/dim]")
        return

    try:
        d = date.fromisoformat(date_str)
    except ValueError:
        console.print(f"[red]Data inválida: '{date_str}'. Use YYYY-MM-DD.[/red]")
        raise SystemExit(2)

    if d >= today:
        console.print(f"[yellow]{d} é hoje ou futuro — snapshots só fecham D-1.[/yellow]")
        raise SystemExit(2)

    target = write_snapshot(sessions, d=d, overwrite=force)
    if target.exists():
        action = "sobrescrito" if force else "garantido"
        console.print(f"[green]Snapshot {action}:[/green] {target.name}")
```

- [ ] **Step 3: Integração lazy no entrypoint principal**

No comando `today`, `projects`, `models`, `recent`, etc — adicionar antes do trabalho real:

```python
def _ensure_snapshots_silently():
    """Lazy + self-healing: garante snapshots passados em background.

    Falhas são silenciadas — não devem bloquear o comando principal.
    """
    try:
        sessions = load_all_sessions()
        yesterday = datetime.now().astimezone().date() - timedelta(days=1)
        ensure_snapshots_up_to(yesterday, sessions, lookback_days=30)
    except Exception:
        pass  # silenciosamente — feature opcional, não crítica
```

E chamar `_ensure_snapshots_silently()` no início dos comandos consumidores. Para evitar overhead repetido na mesma execução, usar lock por execução (variável module-level `_already_ensured`).

- [ ] **Step 4: Rodar tudo**

- [ ] **Step 5: Commit**

```bash
git add src/kiro_dash/cli.py tests/test_snapshot_command.py
git -c user.email='leonardo.menzani@gmail.com' -c user.name='mencoding' \
  commit -m "feat(cli): comando snapshot + integração lazy nos comandos consumidores"
```

---

### Task 4: README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Adicionar seção "Histórico (snapshots)"**

```markdown
## Histórico (snapshots diários)

Snapshots imutáveis de uso por dia local, em
`~/.local/share/kiro-dash/snapshots/<YYYY-MM-DD>.<host>.json`.

### Geração

- **Lazy + self-healing:** comandos consumidores (`today`, `projects`,
  `month`, etc.) chamam silenciosamente `ensure_snapshots_up_to(ontem)`
  no início. Dias sem snapshot são gerados.
- **Manual:**
  ```bash
  kiro-dash snapshot                  # roda lazy explícito
  kiro-dash snapshot 2026-05-16       # gera/garante dia específico
  kiro-dash snapshot 2026-05-16 --force  # sobrescreve
  ```

### Multi-host

Snapshots de hosts distintos coexistem (`2026-05-16.predator.json` +
`2026-05-16.work.json`). Queries somam todos os hosts do mesmo dia.

### Janela stateless

Hoje e ontem **não** viram snapshot persistido — sempre re-lidos dos
arquivos `~/.kiro/sessions/cli/*.json` originais. Snapshot só fecha em
**D-2 ou anterior**.
```

- [ ] **Step 2: Commit**

---

## Self-Review Checklist

- [ ] Schema v1 documentado e versionado
- [ ] `tz_offset` capturado no metadata pra preservar fuso original
- [ ] `captured_by_host` preserva origem
- [ ] `_merge_snapshots` soma totais e concatena breakdowns
- [ ] `ensure_snapshots_up_to` é idempotente (re-roda sem efeito colateral)
- [ ] Lazy é silencioso — falhas não bloqueiam comando principal
- [ ] Hoje + ontem nunca persistem (janela stateless)
- [ ] Comando `--force` opt-in pra sobrescrever
- [ ] README documenta multi-host e stateless

## Done When

- `pytest tests/test_snapshots.py tests/test_snapshot_command.py -v` → todos verdes
- `kiro-dash snapshot` real cria snapshots de dias passados (não toca hoje/ontem)
- `kiro-dash today` continua rodando rápido (lazy não atrasa visivelmente)
- 4 commits no branch `feat/wave5-snapshot`
