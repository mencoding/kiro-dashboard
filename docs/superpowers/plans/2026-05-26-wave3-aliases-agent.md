# Wave 3 / Frente H — Project aliases + heurística completa + filtro --agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar (1) override declarativo `[project_aliases]` no config TOML que vence sobre a heurística; (2) regra `cwd == HOME` → `home` mais fallback `~/Downloads|~/Documents|~/Desktop` para reduzir literais; (3) flag `--agent <name>` em `today/projects/models/recent` para isolar atividade por agent (Nyx, kiro_default, etc.). Tudo aditivo sobre o que já existe na Wave 2.

**Architecture:**

- Config schema ganha `[project_aliases]` (mapping `path → label`). Match prefixo, primeiro hit vence.
- `project_label(cwd, aliases=None)` aceita aliases opcional; quando vazio, comportamento Wave 2.
- CLI carrega aliases via `load_plan_config(...)` e injeta nas chamadas.
- `--agent` filtra `(session, turn)` antes dos agregadores; comparação por igualdade exata em `session.agent_name`.

**Tech Stack:** Python 3.12, sem novas deps.

**Branch:** `feat/wave3-aliases-agent`

---

## File Structure

| Arquivo | Responsabilidade | Mudança |
|---|---|---|
| `src/kiro_dash/config.py` | Adicionar `aliases: dict[str, str]` no `PlanConfig` ou módulo paralelo `ProjectAliases` | **Modificar** |
| `src/kiro_dash/project.py` | `project_label(cwd, aliases=None)` + regra HOME + fallbacks | **Modificar** |
| `src/kiro_dash/aggregator.py` | Helper `filter_by_agent(pairs, agent)` | **Modificar** |
| `src/kiro_dash/cli.py` | `--agent` em today/projects/models/recent; carregar aliases | **Modificar** |
| `tests/test_project.py` | Testes de aliases + HOME + fallbacks | **Modificar** |
| `tests/test_config.py` | Round-trip de `[project_aliases]` | **Modificar** |
| `tests/test_cli_projects_models_recent.py` | Smoke `--agent` | **Modificar** |

---

### Task 1: Persistir `[project_aliases]` no TOML

**Files:**
- Modify: `src/kiro_dash/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Escrever testes**

Acrescentar em `tests/test_config.py`:

```python
def test_load_aliases_returns_empty_when_section_absent(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("[plan]\ntier='free'\nmonthly_credits=50\ncycle_start='2026-05-01'\n")
    aliases = load_aliases(cfg)
    assert aliases == {}


def test_load_aliases_roundtrip(tmp_path):
    cfg = tmp_path / "config.toml"
    save_aliases(
        {"/srv/work/clientes/acme": "acme", "/home/foo/lab": "experimentos"},
        cfg,
    )
    aliases = load_aliases(cfg)
    assert aliases == {
        "/srv/work/clientes/acme": "acme",
        "/home/foo/lab": "experimentos",
    }


def test_load_aliases_preserves_plan_section(tmp_path):
    cfg = tmp_path / "config.toml"
    save_plan(PlanConfig("pro", 1000, date(2026, 5, 1)), cfg)
    save_aliases({"/x": "y"}, cfg)
    p = load_plan(cfg)
    aliases = load_aliases(cfg)
    assert p.tier == "pro"
    assert aliases == {"/x": "y"}
```

- [ ] **Step 2: Rodar — falha (sem `load_aliases`/`save_aliases`)**

```bash
cd /home/menzani/Desenvolvimento/mencoding/kiro-dash
source .venv/bin/activate
pytest tests/test_config.py -v
```

- [ ] **Step 3: Implementar**

Em `src/kiro_dash/config.py`, adicionar:

```python
def load_aliases(path: Path | None = None) -> dict[str, str]:
    """Carrega seção ``[project_aliases]`` do config TOML.

    Aliases são pares ``path → label`` aplicados antes da heurística.
    Retorna ``{}`` quando arquivo não existe ou seção ausente.
    """
    p = path or default_config_path()
    if not p.exists():
        return {}
    with open(p, "rb") as f:
        data = tomllib.load(f)
    section = data.get("project_aliases") or {}
    return {str(k): str(v) for k, v in section.items()}


def save_aliases(aliases: dict[str, str], path: Path | None = None) -> None:
    """Grava ``aliases`` na seção ``[project_aliases]`` preservando outras seções."""
    p = path or default_config_path()
    p.parent.mkdir(parents=True, exist_ok=True)

    existing: dict = {}
    if p.exists():
        with open(p, "rb") as f:
            existing = tomllib.load(f)

    existing["project_aliases"] = dict(aliases)

    with open(p, "wb") as f:
        tomli_w.dump(existing, f)
```

- [ ] **Step 4: Rodar — passa**

```bash
pytest tests/test_config.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/kiro_dash/config.py tests/test_config.py
git -c user.email='leonardo.menzani@gmail.com' -c user.name='mencoding' \
  commit -m "feat(config): seção [project_aliases] no TOML com round-trip"
```

---

### Task 2: `project_label` aceita aliases + cobre HOME/Downloads/Documents

**Files:**
- Modify: `src/kiro_dash/project.py`
- Modify: `tests/test_project.py`

- [ ] **Step 1: Escrever testes**

Acrescentar em `tests/test_project.py`:

```python
def test_alias_vence_heuristica(home):
    cwd = str(home / "iris/projetos/institucional/auto-normas")
    aliases = {str(home / "iris/projetos/institucional/auto-normas"): "auto-normas-custom"}
    assert project_label(cwd, aliases=aliases) == "auto-normas-custom"


def test_alias_match_por_prefixo(home):
    cwd = str(home / "lab/exp-001/sub")
    aliases = {str(home / "lab"): "experimentos"}
    assert project_label(cwd, aliases=aliases) == "experimentos"


def test_alias_mais_especifico_vence(home):
    cwd = str(home / "lab/exp-001/data")
    aliases = {
        str(home / "lab"): "experimentos",
        str(home / "lab/exp-001"): "exp-001",
    }
    assert project_label(cwd, aliases=aliases) == "exp-001"


def test_alias_vazio_devolve_heuristica(home):
    cwd = str(home / "nyx/memory")
    assert project_label(cwd, aliases={}) == "nyx"
    assert project_label(cwd, aliases=None) == "nyx"


def test_home_puro_vira_home(home):
    assert project_label(str(home)) == "home"


def test_downloads_documents_desktop_fallback(home):
    assert project_label(str(home / "Downloads")) == "home/Downloads"
    assert project_label(str(home / "Documents/x")) == "home/Documents"
    assert project_label(str(home / "Desktop")) == "home/Desktop"
```

- [ ] **Step 2: Rodar — falha**

```bash
pytest tests/test_project.py -v
```

- [ ] **Step 3: Implementar — assinatura nova com aliases + regras adicionais**

Substituir corpo de `project_label`:

```python
def project_label(
    cwd: str | None,
    *,
    aliases: dict[str, str] | None = None,
) -> str:
    """Mapeia ``cwd`` para um label conceitual de projeto.

    Ordem de aplicação:

    1. Aliases declarativos (match por prefixo; mais específico vence)
    2. Regras heurísticas hardcoded
    3. Fallback literal

    Aliases são opcionais; comportamento sem aliases é idêntico ao da Wave 2.
    """
    if not cwd:
        return "?"

    # 1. Aliases — match por prefixo (longest match wins)
    if aliases:
        sorted_aliases = sorted(aliases.items(), key=lambda kv: -len(kv[0]))
        for alias_path, label in sorted_aliases:
            if cwd == alias_path or cwd.startswith(alias_path.rstrip("/") + "/"):
                return label

    # 2. Heurística hardcoded
    home = _home_root()

    # iris/projetos/<categoria>/<projeto>
    m = re.match(
        rf"^{re.escape(home)}/iris/projetos/([^/]+)/([^/]+)(?:/.*)?$",
        cwd,
    )
    if m:
        cat, proj = m.group(1), m.group(2)
        if cat in _KNOWN_CATEGORIES:
            return f"{cat}/{proj}"

    if cwd.startswith(f"{home}/iris/projetos/normativos"):
        return "iris-normativos"
    if cwd.startswith(f"{home}/iris/projetos/referencias"):
        return "iris-referencias"
    if cwd == f"{home}/iris/projetos" or cwd.startswith(f"{home}/iris/projetos/"):
        return "iris-projetos"
    if cwd == f"{home}/iris" or cwd.startswith(f"{home}/iris/"):
        return "iris-geral"

    m = re.match(
        rf"^{re.escape(home)}/Desenvolvimento/ifsp/([^/]+)/([^/]+)(?:/.*)?$",
        cwd,
    )
    if m:
        return f"ifsp/{m.group(1)}/{m.group(2)}"

    m = re.match(
        rf"^{re.escape(home)}/Desenvolvimento/([^/]+)/([^/]+)(?:/.*)?$",
        cwd,
    )
    if m:
        return f"{m.group(1)}/{m.group(2)}"

    if cwd == f"{home}/nyx" or cwd.startswith(f"{home}/nyx/"):
        return "nyx"

    # 3. Cobertura adicional do HOME e suas subpastas comuns
    if cwd == home:
        return "home"
    for sub in ("Downloads", "Documents", "Desktop"):
        if cwd == f"{home}/{sub}" or cwd.startswith(f"{home}/{sub}/"):
            return f"home/{sub}"

    # Outros paths sob HOME
    if cwd.startswith(f"{home}/"):
        return cwd[len(home) + 1:]

    return cwd
```

- [ ] **Step 4: Rodar — passa**

```bash
pytest tests/test_project.py -v
```

Expected: 26 PASSED (20 antigos + 7 novos = 27, ajustar conforme contagem real).

- [ ] **Step 5: Commit**

```bash
git add src/kiro_dash/project.py tests/test_project.py
git -c user.email='leonardo.menzani@gmail.com' -c user.name='mencoding' \
  commit -m "feat(project): aliases declarativos + cwd==HOME + Downloads/Documents/Desktop"
```

---

### Task 3: Plugar aliases em `aggregate_by_project` e na CLI

**Files:**
- Modify: `src/kiro_dash/aggregator.py`
- Modify: `src/kiro_dash/cli.py`

- [ ] **Step 1: Modificar `aggregate_by_project` para aceitar aliases**

Em `aggregator.py`:

```python
def aggregate_by_project(
    pairs: list[tuple[Session, Turn]],
    *,
    aliases: dict[str, str] | None = None,
) -> list[Aggregate]:
    """Agrega por ``project_label(s.cwd, aliases=aliases)`` — Wave 3 ganho aliases."""
    return _aggregate_pairs(
        pairs,
        key=lambda s, t: project_label(s.cwd, aliases=aliases),
    )
```

- [ ] **Step 2: Modificar comandos `today/projects` para carregar aliases**

Em `cli.py`, no início de `today` e `projects`:

```python
aliases = load_aliases(default_config_path())
# ...
aggregate_by_project(pairs, aliases=aliases)
```

Importar `load_aliases` no topo.

- [ ] **Step 3: Smoke**

```bash
# Sem aliases (comportamento Wave 2):
kiro-dash projects --window cycle

# Com alias declarado:
kiro-dash plan get  # ver path do config
echo '[project_aliases]' >> ~/.config/kiro-dash/config.toml
echo '"/home/menzani/nyx" = "agente-nyx"' >> ~/.config/kiro-dash/config.toml
kiro-dash projects --window cycle  # label deve aparecer "agente-nyx"
# Limpar
sed -i '/\[project_aliases\]/,$d' ~/.config/kiro-dash/config.toml
```

- [ ] **Step 4: Rodar testes existentes — não devem regredir**

```bash
pytest tests/ -v
```

- [ ] **Step 5: Commit**

```bash
git add src/kiro_dash/aggregator.py src/kiro_dash/cli.py
git -c user.email='leonardo.menzani@gmail.com' -c user.name='mencoding' \
  commit -m "feat(cli): today/projects honram aliases do config TOML"
```

---

### Task 4: Subcomando `aliases get/set/unset`

**Files:**
- Modify: `src/kiro_dash/cli.py`
- Modify: `tests/test_plan_command.py` (acrescentar testes; renomear não é necessário)

- [ ] **Step 1: Escrever testes**

Acrescentar em `tests/test_plan_command.py` (ou criar `tests/test_aliases_command.py`):

```python
def test_aliases_get_lista_existentes(tmp_path, monkeypatch):
    cfg = tmp_path / "config.toml"
    save_aliases({"/x": "alpha", "/y": "beta"}, cfg)
    monkeypatch.setattr("kiro_dash.cli.default_config_path", lambda: cfg)
    runner = CliRunner()
    result = runner.invoke(main, ["aliases", "get"])
    assert result.exit_code == 0
    assert "alpha" in result.output
    assert "beta" in result.output


def test_aliases_set_persiste(tmp_path, monkeypatch):
    cfg = tmp_path / "config.toml"
    monkeypatch.setattr("kiro_dash.cli.default_config_path", lambda: cfg)
    runner = CliRunner()
    result = runner.invoke(main, ["aliases", "set", "/srv/foo", "foo-projeto"])
    assert result.exit_code == 0
    assert load_aliases(cfg) == {"/srv/foo": "foo-projeto"}


def test_aliases_unset_remove(tmp_path, monkeypatch):
    cfg = tmp_path / "config.toml"
    save_aliases({"/x": "alpha", "/y": "beta"}, cfg)
    monkeypatch.setattr("kiro_dash.cli.default_config_path", lambda: cfg)
    runner = CliRunner()
    result = runner.invoke(main, ["aliases", "unset", "/x"])
    assert result.exit_code == 0
    assert load_aliases(cfg) == {"/y": "beta"}
```

- [ ] **Step 2: Implementar**

Em `cli.py`:

```python
@main.group()
def aliases() -> None:
    """Gestão de aliases declarativos de projeto."""


@aliases.command("get")
def aliases_get() -> None:
    """Lista aliases atuais."""
    al = load_aliases(default_config_path())
    if not al:
        console.print("[dim]Nenhum alias declarado.[/dim]")
        return
    table = Table(title="Aliases", show_header=True)
    table.add_column("path")
    table.add_column("label")
    for path, label in sorted(al.items()):
        table.add_row(path, label)
    console.print(table)


@aliases.command("set")
@click.argument("path")
@click.argument("label")
def aliases_set(path: str, label: str) -> None:
    """Define alias ``path → label``. Sobrescreve se já existir."""
    al = load_aliases(default_config_path())
    al[path] = label
    save_aliases(al, default_config_path())
    console.print(f"[green]Alias salvo:[/green] {path} → {label}")


@aliases.command("unset")
@click.argument("path")
def aliases_unset(path: str) -> None:
    """Remove alias por path."""
    al = load_aliases(default_config_path())
    if path not in al:
        console.print(f"[yellow]Alias não encontrado: {path}[/yellow]")
        raise SystemExit(1)
    del al[path]
    save_aliases(al, default_config_path())
    console.print(f"[green]Alias removido:[/green] {path}")
```

- [ ] **Step 3: Rodar — passa**

```bash
pytest tests/test_plan_command.py -v
```

- [ ] **Step 4: Commit**

```bash
git add src/kiro_dash/cli.py tests/test_plan_command.py
git -c user.email='leonardo.menzani@gmail.com' -c user.name='mencoding' \
  commit -m "feat(cli): subgrupo aliases get/set/unset"
```

---

### Task 5: Flag `--agent` em `today/projects/models/recent`

**Files:**
- Modify: `src/kiro_dash/aggregator.py`
- Modify: `src/kiro_dash/cli.py`
- Modify: `tests/test_aggregator.py`
- Modify: `tests/test_cli_projects_models_recent.py`

- [ ] **Step 1: Escrever teste do helper**

Em `tests/test_aggregator.py`:

```python
from kiro_dash.aggregator import filter_by_agent


def test_filter_by_agent_isola_uma():
    s_nyx = make_session(agent_name="nyx", turns=[make_turn(credits=10)])
    s_other = make_session(session_id="x", agent_name="kiro_default", turns=[make_turn(credits=5)])
    pairs = [(s, t) for s in (s_nyx, s_other) for t in s.turns]
    out = filter_by_agent(pairs, "nyx")
    assert len(out) == 1
    assert out[0][0].agent_name == "nyx"


def test_filter_by_agent_sem_match_devolve_vazio():
    s = make_session(agent_name="nyx", turns=[make_turn()])
    pairs = [(s, t) for t in s.turns]
    out = filter_by_agent(pairs, "inexistente")
    assert out == []


def test_filter_by_agent_none_passa_tudo():
    s = make_session(agent_name="nyx", turns=[make_turn()])
    pairs = [(s, t) for t in s.turns]
    out = filter_by_agent(pairs, None)
    assert out == pairs
```

- [ ] **Step 2: Rodar — falha**

```bash
pytest tests/test_aggregator.py -v -k filter_by_agent
```

- [ ] **Step 3: Implementar helper**

Em `aggregator.py`:

```python
def filter_by_agent(
    pairs: list[tuple[Session, Turn]],
    agent: str | None,
) -> list[tuple[Session, Turn]]:
    """Filtra pares pelo ``agent_name`` da sessão. ``None`` passa tudo."""
    if agent is None:
        return pairs
    return [(s, t) for (s, t) in pairs if s.agent_name == agent]
```

- [ ] **Step 4: Plugar `--agent` em CLI**

Em `today`, `projects`, `models`, `recent` adicionar:

```python
@click.option("--agent", default=None, help="Filtra por agent_name (ex: nyx, kiro_default).")
```

E aplicar `filter_by_agent(pairs, agent)` antes de cada agregação.

- [ ] **Step 5: Smoke**

```bash
kiro-dash today --agent nyx
kiro-dash projects --agent nyx --window cycle
kiro-dash models --agent inexistente  # deve mostrar "sem turns na janela"
```

- [ ] **Step 6: Adicionar teste de smoke CLI**

Em `tests/test_cli_projects_models_recent.py`:

```python
def test_today_filter_by_agent_nao_quebra():
    with patch("kiro_dash.cli.load_all_sessions", return_value=_fake_sessions()):
        runner = CliRunner()
        result = runner.invoke(main, ["today", "--agent", "kiro_default"])
    assert result.exit_code == 0
```

- [ ] **Step 7: Rodar tudo**

```bash
pytest tests/ -v
```

- [ ] **Step 8: Commit**

```bash
git add src/kiro_dash/aggregator.py src/kiro_dash/cli.py tests/test_aggregator.py tests/test_cli_projects_models_recent.py
git -c user.email='leonardo.menzani@gmail.com' -c user.name='mencoding' \
  commit -m "feat(cli): --agent filter em today/projects/models/recent"
```

---

### Task 6: README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Adicionar seções**

Antes da Licença:

```markdown
## Aliases de projeto (override declarativo)

Aliases têm prioridade sobre a heurística. Match por prefixo: o mais
específico vence.

```bash
kiro-dash aliases set /srv/work/clientes/acme acme
kiro-dash aliases set /home/foo/lab experimentos
kiro-dash aliases get
kiro-dash aliases unset /srv/work/clientes/acme
```

Persistido em `~/.config/kiro-dash/config.toml` na seção
`[project_aliases]`.

## Filtro por agent

```bash
kiro-dash today --agent nyx
kiro-dash projects --agent kiro_default --window cycle
kiro-dash models --agent nyx --window month
kiro-dash recent --agent nyx
```

`--agent <name>` isola a atividade de um agent específico (comparação
por igualdade exata em `session.agent_name`).
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git -c user.email='leonardo.menzani@gmail.com' -c user.name='mencoding' \
  commit -m "docs: aliases declarativos e flag --agent"
```

---

## Self-Review Checklist

- [ ] Aliases match por prefixo, longest-match-wins
- [ ] `project_label` mantém compat com chamadas sem `aliases` (default `None`)
- [ ] `cwd == HOME` → `home`; subpastas comuns viram `home/<X>`
- [ ] `--agent` aceita qualquer string; sem match retorna vazio gracefully
- [ ] Comandos `aliases get/set/unset` persistem no mesmo TOML que `plan`
- [ ] README documenta as 2 features novas

## Done When

- `pytest tests/ -v` → todos verdes (incluindo Wave 1, 2)
- Smoke: `kiro-dash aliases set /home/menzani/nyx agente-nyx && kiro-dash projects --window cycle` mostra `agente-nyx`
- Smoke: `kiro-dash today --agent nyx` filtra corretamente (testar quando houver sessão `nyx` real)
- 6 commits no branch `feat/wave3-aliases-agent`
