# Wave 6 / Frente Q — `IdeSessionBackend` para sessões IDE

**Branch:** `feat/wave6-ide-sessions`
**Esforço:** 8-10h
**Depende de:** P (Backend ABC + sources.py + freshness)
**Entrega:** sessões do Kiro IDE (chat, do, spec) acessíveis via comandos do kiro-dash, com créditos por turn extraídos dos arquivos de execution e classificação de intent disponível como dimensão extra.

## Objetivo

Trazer as sessões do Kiro IDE para o domínio do kiro-dash com paridade
máxima possível com o backend CLI. Ao final desta frente, comandos
como `today`, `projects`, `models`, `recent`, `tools` e `session` já
**enxergam** sessões IDE, embora o **somatório multi-source** (CLI ∪
IDE no mesmo agregado) só fique completo na frente R.

Em isolamento, o usuário pode listar sessões IDE com flag explícita ou
configurando `[sources].default = "ide"` no config.

## Pré-condições

- Frente P mergeada na `main`
- Fixtures adicionais coletadas durante a frente:
  - 1 turn em modo `do-agent` (Léo executa antes do início desta frente)
  - 1 turn que crie/edite uma `spec` (Léo executa antes desta frente)
  - 1 turn que chame uma tool real (read/write de arquivo via Autopilot)
- Schema observado durante coleta documentado em `docs/adr/0001-multi-backend-architecture.md` (anexo se necessário)

## Decisões consolidadas (revisar antes de codar)

1. **Identidade composta** `ide:<sessionId>` — slug fixo, sessionId UUID nativo do IDE
2. **Workspace path codificado em base64url** com padding por `=` substituído por `_`. Decoder espelha o encoder:
   - `L2hvbWUvbWVuemFuaS9EZXNlbnZvbHZpbWVudG8vbWVuY29kaW5nL2N2YXQtYWRlcHR1cw__` → `/home/menzani/Desenvolvimento/mencoding/cvat-adeptus`
3. **`profile_hash` é opaque** para o kiro-dash. Detectado pela presença do arquivo `f62de366d0006e17ea00a01f6624aabf` (catálogo de executions) dentro de `kiro.kiroagent/<hash>/`. Pode haver múltiplos profile_hash se usuário trocou de conta — todos são lidos
4. **Mapping para tipo interno:**
   - `Session` (kiro-dash) ← `<sessionId>.json` (IDE)
   - `Turn` (kiro-dash) ← cada par `(history[i] user, history[i+1] assistant)` em IDE session, juntado com a execution correspondente para extrair `usageSummary[].usage` (créditos)
   - `ToolCall` ← `actions[]` em execution, filtrado por `actionType == "tool"`
5. **Agent normalizado:** todas sessões IDE têm `agent = "kiro-ide"` no domínio interno. Variabilidade fica no campo novo `workflow_type` ∈ {`chat-agent`, `do-agent`, `spec`}
6. **Modelo:** `selectedModel` quando explícito (`auto`, modelo nomeado), ou `defaultModelTitle` (`Agent`) como fallback. Quando `selectedModel == "auto"`, marcar como `kiro:auto` no domínio interno
7. **Sessão "live":** sem lockfile, heurística é `active: true` no JSON da sessão **+** mtime do arquivo < threshold (default 60s)
8. **Project label:** workspace path do IDE entra na heurística existente de `project.py`; mesma regra de `cwd` do CLI

## Tasks (ordem TDD)

### T1 — Fixtures redatadas

- Coletar com Léo (em sessão paralela ao desenvolvimento) ou usar dummy:
  - `tests/fixtures/ide/sessions/sessions_index.json` — catálogo
  - `tests/fixtures/ide/sessions/<uuid>_chat.json` — sessão chat
  - `tests/fixtures/ide/sessions/<uuid>_do.json` — sessão do
  - `tests/fixtures/ide/sessions/<uuid>_spec.json` — sessão spec
  - `tests/fixtures/ide/executions/executions_index.json` — índice
  - `tests/fixtures/ide/executions/<exec>_chat.json` — execution chat
  - `tests/fixtures/ide/executions/<exec>_do.json` — execution do com tool calls
  - `tests/fixtures/ide/executions/<exec>_spec.json` — execution spec
- Helper `tests/fixtures/ide/build_ide_layout.py` cria o layout completo de filesystem em `tmp_path` para os testes
- Conteúdo de mensagens **redatado** com placeholders curtos (`<user message redacted>`)
- **Commit:** `test(fixtures): layout completo Kiro IDE redatado`

### T2 — `workspace_codec.py`

- Módulo `src/kiro_dash/backends/workspace_codec.py`:
  - `encode(path: str) -> str` — base64url, padding `=` → `_`
  - `decode(encoded: str) -> str` — inverso
- Roundtrip verificado em testes
- Edge cases: paths com caracteres não-ASCII, paths longos
- **Commit:** `feat(ide-sessions): codec base64url com padding underscore`

### T3 — `IdeSessionBackend` skeleton

- `src/kiro_dash/backends/ide_sessions.py`
- `IdeSessionBackend(Backend)` com `slug = "ide"`:
  - `is_available()`:
    - `~/.config/Kiro/User/globalStorage/kiro.kiroagent/workspace-sessions/` existe?
    - Pelo menos um `<base64>/sessions.json` válido?
  - `capabilities() = {SESSIONS, TURNS, TOOL_CALLS, RUNNING}`
- `iter_workspaces() -> Iterator[Workspace]` — varre `workspace-sessions/*/`
- `Workspace` dataclass: `path: str` (decoded), `sessions_index: list[SessionIndexEntry]`
- **Tests:** detecção em fixture
- **Commit:** `feat(ide-sessions): IdeSessionBackend.is_available + Workspace iter`

### T4 — Reader de catálogo + sessão individual

- `read_sessions_index(workspace_dir) -> list[SessionIndexEntry]`
- `read_session(session_id, workspace_dir) -> IdeSession` — typed model com:
  - `session_id`, `workspace_path`, `title`, `date_created`
  - `selected_model`, `default_model_title`, `autonomy_mode`, `session_type`
  - `history: list[IdeHistoryItem]` (sem conteúdo, só presença de message + role)
  - `context_usage_percentage: float`
  - `active: bool`, `mtime: datetime`
- **Tests:** parsing das 3 fixtures (chat/do/spec)
- **Commit:** `feat(ide-sessions): typed reader de session.json`

### T5 — Reader de executions catalog

- `read_executions_index(profile_hash_dir) -> list[ExecutionIndexEntry]`
- `iter_executions() -> Iterator[ExecutionIndexEntry]` enumera **todos** os profile_hash dentro de `kiro.kiroagent/`
- **Tests:** múltiplos profile_hash, executions em ordem
- **Commit:** `feat(ide-sessions): index reader cobrindo múltiplos profile_hash`

### T6 — Reader de execution completa

- `read_execution(execution_id) -> IdeExecution`
- Resolve qual profile_hash dir contém via index
- Typed model `IdeExecution`:
  - `execution_id`, `chat_session_id` (link com IdeSession)
  - `workflow_type` ∈ {`chat-agent`, `do-agent`, `spec`}
  - `start_time`, `end_time`, `status` ∈ {`succeed`, `failed`, ...}
  - `actions: list[IdeAction]` — typed por actionType
  - `usage_summary: list[IdeUsageEntry]` — `usage`, `unit`, `unit_plural`
  - `intent_result: Optional[IdeIntent]` quando há `intentClassification` em actions
  - `context_usage_percentage: float`
- **Tests:** parsing das 3 fixtures + ausência graciosa de campos opcionais
- **Commit:** `feat(ide-sessions): typed reader de execution com actions/usage/intent`

### T7 — Mapper IDE → tipo interno do kiro-dash

- `src/kiro_dash/backends/ide_mapper.py`
- `to_session(ide_session, executions_for_session) -> Session` (tipo interno)
- `to_turn(ide_session.history_pair, execution) -> Turn`
  - Créditos do turn: somar `usage` de `usage_summary` da execution correspondente
  - Modelo: `selectedModel` (ou `kiro:auto` se "auto")
  - Workflow type vai em `Turn.metadata["workflow_type"]`
- `to_tool_calls(execution.actions) -> list[ToolCall]`:
  - Filtra `actionType == "tool"`; cada uma vira ToolCall
  - `actionType == "intentClassification"` vira ToolCall metadata especial (pode ser oculto na listagem default; opt-in via flag em Q ou R)
- **Tests:** roundtrip de cada workflow_type para Session/Turn/ToolCall
- **Commit:** `feat(ide-sessions): mapper schema IDE → tipo interno kiro-dash`

### T8 — `IdeSessionBackend.list_sessions()` + `iter_turns()`

- API pública do backend espelhando `CliJsonBackend`:
  - `list_sessions(filters) -> list[Session]`
  - `iter_turns(session_id) -> Iterator[Turn]`
  - `iter_tool_calls(session_id) -> Iterator[ToolCall]`
  - `running_sessions() -> list[Session]` — heurística active+mtime
  - `data_age()` retorna idade da sessão mais recentemente modificada (ou `None` se sem dados)
- **Tests:** integração com mapper, comportamento equivalente ao CLI
- **Commit:** `feat(ide-sessions): API list/iter equivalente ao CliJsonBackend`

### T9 — Detecção de sessão live sem lockfile

- Heurística em `running_sessions()`:
  - `session.active == True` E `mtime > now - threshold` → live
  - Threshold default 60s, configurável `[ide_sessions].live_threshold_seconds`
- Cuidado: IDE pode ficar com `active: false` mas sessão ainda em uso (idle entre turns). A heurística é melhor-esforço, documentar limitação no help do `audit running`
- **Tests:** sessões active+fresh, active+stale, inactive+fresh, inactive+stale
- **Commit:** `feat(ide-sessions): heurística sessão live sem lockfile`

### T10 — `Sources.ide_sessions` + integração no detector

- Atualizar `sources.py`: `ide_sessions: Optional[IdeSessionBackend]`
- `Sources.detect()` instancia e checa
- `whoami` agora exibe IDE sessions fonte com contagem de sessões e idade
- **Tests:** detector com Q ativo
- **Commit:** `feat(sources): registrar IdeSessionBackend no detector`

### T11 — CLI: comandos individuais consultam IDE

Modificações que **não fazem dedup ainda** (R faz isso). Cada comando aprende a perguntar ao IDE em paralelo:

- `recent --source ide` → só IDE
- `recent --source cli` → só CLI (default atual)
- `recent --source all` → concatena (sem dedup), mostra coluna source
- Mesma lógica para `today`, `projects`, `models`, `tools`, `session`
- Default mantém `cli` para não quebrar comportamento atual sem flag explícita
- **Tests:** cada comando × cada source × cenário sem fontes
- **Commit:** `feat(cli): flag --source em listings, sem dedup ainda`

### T12 — Coluna source em outputs

- Quando `--source all` ou `--show-source` é passado, output ganha coluna `source` (cli/ide)
- Default sem `--source`: coluna oculta (preserva layout atual)
- **Tests:** rendering com/sem flag
- **Commit:** `feat(cli): coluna source em listings com --show-source`

### T13 — MCP: tools de sessão também olham IDE

- `today_summary`, `top_projects`, `top_models`, `active_sessions`, `session_details` aceitam parâmetro opcional `source` (default `"cli"` para retro-compat de chamadas antigas — Wave 6 muda default para `"all"` em R)
- Schema da tool atualizado
- **Tests:** smoke MCP com source explícito
- **Commit:** `feat(mcp): tools de sessão suportam parâmetro source`

### T14 — Documentação

- README seção `Sessões IDE` na arquitetura
- Tabela mostrando equivalências CLI×IDE para cada comando
- Documentar `KIRO_DASH_IDE_SESSIONS_ROOT`, `KIRO_DASH_NO_IDE_SESSIONS`
- Limitação documentada: heurística live sem lockfile, intent classification como metadata extra
- **Commit:** `docs: README — sessões IDE e flag --source`

## Configuração (escopo da frente Q)

### Variáveis de ambiente

| Var | Default | Propósito |
|---|---|---|
| `KIRO_DASH_IDE_SESSIONS_ROOT` | `~/.config/Kiro/User/globalStorage/kiro.kiroagent/` | override do path |
| `KIRO_DASH_NO_IDE_SESSIONS` | unset | desabilita leitura de sessões IDE |

### CLI flags

| Comando | Flag | Propósito |
|---|---|---|
| `today`, `projects`, `models`, `recent`, `tools`, `session`, `audit *` | `--source cli\|ide\|all` | filtro de fonte |
| listings | `--show-source` | mostra coluna source |

### Config (`~/.config/kiro-dash/config.toml`)

```toml
[ide_sessions]
live_threshold_seconds = 60      # heurística sessão "live" sem lockfile
include_intent_classification = false   # intent vira ToolCall visível? default false
```

### Códigos de erro

| Código | Onde | Significado |
|---|---|---|
| `IDE_WORKSPACE_DECODE_FAIL` | `workspace_codec.decode` falha | nome de diretório base64url malformado |
| `IDE_EXECUTION_NOT_FOUND` | mapper não encontra execution para `chatSessionId` | turn aparece sem créditos; warning não-fatal |
| `IDE_INTENT_PARSE_FAIL` | `intentResult` ausente ou shape inesperado | metadata extra perdida; warning não-fatal |
| `IDE_PROFILE_HASH_AMBIGUOUS` | múltiplos profile_hash com mesmo execution_id | toma o mais recente, log de aviso |

## Schema fixtures

Em `tests/fixtures/ide/`:

- `sessions/sessions_index.json` — catálogo
- `sessions/<uuid>_chat.json` — sessão chat (turn simples)
- `sessions/<uuid>_do.json` — sessão do com 1 tool call
- `sessions/<uuid>_spec.json` — sessão spec
- `executions/executions_index.json`
- `executions/<exec>_chat.json` — actions: intentClassification + chat
- `executions/<exec>_do.json` — actions: intentClassification + chat + tool
- `executions/<exec>_spec.json` — actions: intentClassification + spec workflow específico
- `build_ide_layout.py` — monta a árvore de fs em `tmp_path`

## Critérios de aceitação

- [ ] `pytest tests/ -v` 100% verde
- [ ] `kiro-dash recent --source ide` lista sessões IDE
- [ ] `kiro-dash recent --source all` concatena CLI+IDE com coluna source
- [ ] `kiro-dash session <prefix>` resolve prefix em ambas fontes; ambíguo → pede desambiguação com slug
- [ ] `kiro-dash today --source ide` agrega só IDE
- [ ] `kiro-dash audit running --source all` lista sessões live de ambas fontes (com a limitação documentada da heurística IDE)
- [ ] `kiro-dash whoami` mostra IDE sessions com contagem
- [ ] MCP tools aceitam `source` parameter
- [ ] Sem regressão nos comandos sem `--source` (default `cli` preserva comportamento)
- [ ] Documentação README atualizada com tabela de equivalências
- [ ] Fixtures cobertas com 3 workflow_types (chat/do/spec)

## Pendências fora desta frente

- Dedup CLI ∩ IDE em `--source all` — frente R
- Aggregator multi-source nas queries históricas (`month`, `year`, `compare`) — frente R
- Snapshots schema bump — frente R
- Sync (rclone) cobrindo workspace-sessions IDE — frente R
- TUI ganha filtro source — frente R
- Banner "Kiro IDE detectado" para usuário que tinha só CLI — pode entrar aqui (extra) ou em R
