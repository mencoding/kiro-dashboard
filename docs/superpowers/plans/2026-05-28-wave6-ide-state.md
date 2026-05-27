# Wave 6 / Frente P — `IdeStateBackend` para billing

**Branch:** `feat/wave6-ide-state`
**Esforço:** 4-5h
**Depende de:** —
**Entrega:** billing autoritativo do servidor exposto em `balance`, `plan get`, MCP `usage_state`, com fallback gracioso para estimativa local quando IDE não disponível.

## Objetivo

Resolver a imprecisão atual do `kiro-dash balance` (estimativa local
baseada em `plan set`) trocando-a, quando possível, por leitura direta
do billing autoritativo que o Kiro IDE cacheia em
`~/.config/Kiro/User/globalStorage/state.vscdb`, chave `kiro.kiroAgent`.

Em paralelo, criar a infra de **backends pluggable** descrita no
ADR-0001 (interface `Backend` + módulo `sources.py` detector), que vai
sustentar Q e R nas próximas frentes.

## Pré-condições

- ADR-0001 mergeado em `main` (✓ commit `4ce8230`)
- Repo em `v0.6.1`, working tree limpo
- Fixture inicial do state.vscdb redatada em `tests/fixtures/ide/state_vscdb_kiroagent.json` (criar como parte da task 1)

## Decisões consolidadas (revisar antes de codar)

1. **Schema do `kiro.kiroAgent` é JSON dentro do BLOB do `ItemTable`.** Reader retorna typed model (dataclass `IdeUsageState`)
2. **Connection é one-shot:** abre `?mode=ro` em cada chamada, lê, fecha. Sem connection pool — o frescor importa mais que latência (read é <5ms)
3. **`schema_version_observed`** detectado por presença de campos
   conhecidos (`hasBeenInstalled`, `kiro.resourceNotifications.usageState`).
   Versão atual chamada `1` (não há marker oficial; convencionado pelo
   kiro-dash). Mudança no shape → próxima versão
4. **Fallback no `balance`** mantém estimativa local atual + warning
   visível: *"saldo é estimativa — instale o Kiro IDE e abra-o uma vez para saldo autoritativo"*
5. **`plan get` consome `usageLimit` e `overageRate` quando IDE disponível.** Atualiza `~/.config/kiro-dash/config.toml` com `auto_detected: true` em `[plan]` para distinguir manual vs automático

## Tasks (ordem TDD)

### T1 — Skeleton `Backend` ABC + fixture do state.vscdb

- Criar `src/kiro_dash/backends/__init__.py` com classe abstrata `Backend`:
  - `is_available() -> bool`
  - `data_age() -> Optional[float]` (segundos; `None` se irrelevante)
  - `capabilities() -> set[Capability]` (enum: `USAGE_STATE`, `SESSIONS`, `TURNS`, `RUNNING`, `ACCOUNT`)
  - `slug() -> str`
- Criar `tests/fixtures/ide/state_vscdb_kiroagent.json` — sample real redatado da máquina dev (current usage zerado para evitar leak de uso real)
- Criar fixture `tests/fixtures/ide/build_state_vscdb.py` que constrói um sqlite real a partir do JSON (usa `sqlite3` stdlib)
- **Test:** `Backend` ABC não pode ser instanciada; subclass de teste implementa todos métodos
- **Commit:** `feat(backends): introduzir Backend ABC + fixture state.vscdb redatada`

### T2 — Rename `parser.py` para `CliJsonBackend`

- Mover lógica de leitura de sessões CLI para `src/kiro_dash/backends/cli_json.py`
- `CliJsonBackend(Backend)` — wrapper sobre o parser atual, com `slug = "cli"`
- `parser.py` permanece como módulo de helpers de baixo nível (read_session_json, read_jsonl), agora chamado pelo backend
- Atualizar imports em `aggregator.py`, `cli.py`, `cache.py`, `watchdog.py`, `snapshots.py`, `history.py`, `mcp_server.py`
- **Tests:** todos os testes existentes do parser continuam passando após rename
- **Commit:** `refactor(backends): mover parser CLI para CliJsonBackend (compat 100%)`

### T3 — `IdeStateBackend.is_available()` + reader read-only

- Criar `src/kiro_dash/backends/ide_state.py`
- `IdeStateBackend(Backend)` com `slug = "ide"`
- `is_available()`:
  - Path `~/.config/Kiro/User/globalStorage/state.vscdb` existe?
  - Sqlite abre? (lazy, só verifica readability)
  - Tabela `ItemTable` tem chave `kiro.kiroAgent`?
  - Schema reconhecido (campos esperados presentes)?
- Helper `_open_ro()` retorna conexão `?mode=ro&immutable=0` com retry em `SQLITE_BUSY` (max 3 tentativas, 50ms entre)
- **Tests:** fixture conhecida → `is_available() == True`; fixture sem chave → `False`; arquivo inexistente → `False`
- **Commit:** `feat(ide-state): IdeStateBackend.is_available com schema check`

### T4 — `IdeUsageState` typed model + `read_usage_state()`

- Adicionar dataclass `IdeUsageState` em `backends/ide_state.py`:
  ```python
  @dataclass(frozen=True)
  class IdeUsageState:
      current_usage: float
      usage_limit: float
      percentage_used: float
      current_overages: float
      overage_cap: float
      overage_rate: float
      reset_date: datetime
      currency_code: str         # "USD"
      currency_symbol: str       # "$"
      unit: str                  # "INVOCATIONS"
      timestamp: datetime
      schema_version_observed: int  # 1 (atual)
  ```
- `IdeStateBackend.read_usage_state() -> Optional[IdeUsageState]`
- `data_age()` retorna `(now - timestamp).total_seconds()`
- **Tests:** parsing de fixture válida; campos faltando → erro claro `IDE_STATE_SCHEMA_UNKNOWN`
- **Commit:** `feat(ide-state): typed IdeUsageState + parser do JSON do BLOB`

### T5 — Helper de frescor compartilhado

- Criar `src/kiro_dash/freshness.py`:
  - `FreshnessLevel` enum: `GREEN`, `YELLOW`, `RED`, `GRAY`
  - `freshness_for(age_seconds: float, config: dict) -> FreshnessLevel`
  - `format_age(age_seconds: float) -> str` (humanize: "47s", "3m", "2h", "1d")
  - `format_freshness_badge(level, age) -> str` com cor rich
- Defaults: green ≤ 3h, yellow ≤ 12h, red ≤ 24h, gray > 24h
- Config override via `[freshness]` em `config.toml`
- **Tests:** fronteiras (2:59h vs 3:00h, etc.), formatação de idade
- **Commit:** `feat(freshness): helper de classificação por idade do dado`

### T6 — `sources.py` detector

- Criar `src/kiro_dash/sources.py`:
  - `Sources` class com `cli_json: CliJsonBackend`, `ide_state: IdeStateBackend`, `cli_sqlite: None`, `ide_sessions: None` (placeholders para Q/R)
  - `Sources.detect() -> Sources` factory que instancia e checa `is_available()`
  - `available_for(capability) -> list[Backend]` retorna em ordem de preferência
  - `summary() -> str` para `whoami`
- **Tests:** combinações (só CLI, só IDE, ambos, nenhum)
- **Commit:** `feat(sources): detector runtime de backends disponíveis`

### T7 — CLI: `kiro-dash balance` lê IDE quando disponível

- Em `cli.py` comando `balance`:
  - Tentar `Sources.detect().available_for(Capability.USAGE_STATE)`
  - Se IDE disponível → exibir `currentUsage / usageLimit` + badge de frescor + dias até `resetDate`
  - Senão → fallback estimativa local atual + warning `IDE_STATE_UNAVAILABLE` em cinza com hint de instalação
  - Flag `--no-ide` força ignorar IDE
- Output exemplo (IDE):
  ```
  Saldo: 1598.83 / 10000 invocations (15.99%)
  Reset em: 2026-06-01 (4 dias)
  Overage rate: $0.04/invocation acima de 10000
  Fonte: ide  ·  snapshot 47s atrás  [verde]
  ```
- Output exemplo (sem IDE):
  ```
  Saldo (estimativa local): 421 / 1000 cr (42.1%)
  Para saldo autoritativo: instale o Kiro IDE (https://kiro.dev/downloads/)
                            e abra-o pelo menos uma vez para refresh.
  ```
- **Tests:** ambos cenários
- **Commit:** `feat(cli): balance lê billing autoritativo do IDE com fallback`

### T8 — CLI: `kiro-dash plan get` auto-detect

- Em `cli.py` comando `plan get`:
  - Se IDE disponível e `[plan]` em config.toml está em modo `auto_detected: true` ou unset → ler do IDE e refletir
  - Se config.toml tem `[plan]` manual (`auto_detected: false`) → respeitar manual e mostrar source: `manual override`
- Não tocar em `plan set` — comportamento atual preservado, mas marca `auto_detected: false` ao salvar
- **Tests:** auto-detect com IDE, manual sobrescreve, sem IDE usa default
- **Commit:** `feat(cli): plan get auto-detecta do IDE quando não-manual`

### T9 — MCP tool `usage_state`

- Em `mcp_server.py` adicionar tool `usage_state`:
  - Retorna dict com todos campos de `IdeUsageState` + `data_age_seconds` + `freshness_level` + `source: "ide"`
  - Se IDE não disponível → erro estruturado `{"error": "IDE_STATE_UNAVAILABLE", "hint": "..."}`
- Atualizar registro de tools (lista exposta no MCP)
- **Tests:** smoke do servidor MCP
- **Commit:** `feat(mcp): tool usage_state expondo billing autoritativo`

### T10 — `whoami` mostra fontes ativas

- `kiro-dash whoami` agora exibe seção `Fontes detectadas`:
  ```
  Fontes detectadas:
    cli       (CliJsonBackend)     ✓  /home/.../.kiro/sessions/cli/
    ide       (IdeStateBackend)    ✓  /home/.../.config/Kiro/.../state.vscdb
                                       snapshot 47s atrás [verde]
    ide       (IdeSessionBackend)  —  (frente Q da Wave 6)
    cli-sqlite                     —  (watchlist; conversations_v2 vazia)
  ```
- **Test:** smoke
- **Commit:** `feat(whoami): expor fontes detectadas com idade de cada uma`

### T11 — Banner de onboarding IDE

- Quando `Sources.detect()` retorna só CLI (sem IDE), exibir banner uma vez por dia em comandos relevantes (`balance`, `plan get`, primeiro `today` da sessão):
  ```
  ℹ️  Saldo de créditos é estimativa local (impreciso após uso cross-device).
     Instale o Kiro IDE para saldo autoritativo do servidor:
     curl -fsSL https://kiro.dev/install/ide | bash
     (Suprima este aviso com KIRO_DASH_NO_BANNER=1)
  ```
- Estado salvo em `~/.cache/kiro-dash/banner_state.json` (último timestamp de exibição)
- **Tests:** banner mostra 1x/dia, suprimido por env var
- **Commit:** `feat(onboarding): banner sugerindo Kiro IDE para saldo real`

### T12 — Documentação

- README: adicionar seção `Saldo autoritativo via Kiro IDE` (na seção Plan e saldo)
- Documentar env vars `KIRO_DASH_IDE_STATE_PATH`, `KIRO_DASH_NO_IDE_STATE`, `KIRO_DASH_NO_BANNER`
- Mencionar política de frescor + tabela de cores
- **Commit:** `docs: README — billing autoritativo via IDE + frescor + envs`

## Configuração (escopo da frente P)

### Variáveis de ambiente

| Var | Default | Propósito |
|---|---|---|
| `KIRO_DASH_IDE_STATE_PATH` | `~/.config/Kiro/User/globalStorage/state.vscdb` | override do path |
| `KIRO_DASH_NO_IDE_STATE` | unset | desabilita leitura do billing IDE (testes/debug) |
| `KIRO_DASH_NO_BANNER` | unset | suprime banner de onboarding |

### CLI flags

| Comando | Flag | Propósito |
|---|---|---|
| `balance` | `--no-ide` | força fallback para estimativa local |
| `plan get` | `--no-ide` | força fallback para config manual |

### Config (`~/.config/kiro-dash/config.toml`)

```toml
[freshness]
green_max_hours = 3
yellow_max_hours = 12
red_max_hours = 24

[plan]
auto_detected = true   # gerenciado automaticamente; false após `plan set`
# tier, credits, cycle_start permanecem como hoje
```

### Códigos de erro

| Código | Onde | Significado |
|---|---|---|
| `IDE_STATE_UNAVAILABLE` | `IdeStateBackend.is_available()=False` | path/db ausente, schema desconhecido |
| `IDE_STATE_STALE` | `data_age > red_max_hours` | warning não-fatal, dado ainda exibido |
| `IDE_STATE_SCHEMA_UNKNOWN` | parsing falha em campos esperados | `kiro.kiroAgent` shape mudou; reportar versão observada |

## Schema fixtures

Em `tests/fixtures/ide/`:

- `state_vscdb_kiroagent.json` — JSON com shape do BLOB redatado (current_usage = 0, sem timestamps reais identificáveis)
- `build_state_vscdb.py` — script Python que constrói sqlite a partir do JSON, executado em `conftest.py` antes dos testes
- `state_vscdb_unknown_schema.json` — variante para testar erro `IDE_STATE_SCHEMA_UNKNOWN`

## Critérios de aceitação

- [ ] `pytest tests/ -v` 100% verde
- [ ] `kiro-dash balance` exibe saldo do IDE quando IDE instalado e fonte fresh
- [ ] `kiro-dash balance --no-ide` cai em estimativa local com warning
- [ ] `kiro-dash plan get` reflete `usageLimit` do IDE quando não-manual
- [ ] `kiro-dash whoami` lista fontes detectadas com idade
- [ ] Banner aparece 1x/dia em CLI-only, suprimido por env var
- [ ] MCP `usage_state` retorna dict completo ou erro estruturado
- [ ] Documentação README atualizada
- [ ] Sem regressão nos comandos existentes (`today`, `projects`, `models`, `tools`, `recent`, `session`, `audit *`, `sync *`, `cache *`, `aliases *`, `month`, `year`, `compare`)
- [ ] Decisão sobre release intermediária v0.6.2 com apenas P (registrada como nota no PR de merge)

## Pendências fora desta frente

- Sessões IDE em si — frente Q
- Filtro `--source` em comandos de listagem — frente R
- TUI mostrando saldo autoritativo na aba Now — pode entrar aqui (extra) ou em R (mais coerente)
- Schema bump v1→v2 dos snapshots — frente R (não acontece em P porque P não escreve snapshots)
