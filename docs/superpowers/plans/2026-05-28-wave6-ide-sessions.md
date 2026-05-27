# Wave 6 / Frente Q — `IdeSessionBackend` para sessões IDE

**Branch:** `feat/wave6-ide-sessions`
**Esforço:** 6-7h (revisado pós-coleta de 2026-05-27)
**Depende de:** P (Backend ABC + sources.py + freshness)
**Entrega:** sessões do Kiro IDE (workflow=chat-agent com intent ∈ {chat,do,spec} + workflow=spec-generation) acessíveis via comandos do kiro-dash, com créditos por turn extraídos das executions e classificação de intent disponível como dimensão extra.

## Objetivo

Trazer as sessões do Kiro IDE para o domínio do kiro-dash com paridade
máxima possível com o backend CLI. Ao final desta frente, comandos
como `today`, `projects`, `models`, `recent`, `tools` e `session` já
**enxergam** sessões IDE, embora o **somatório multi-source** (CLI ∪
IDE no mesmo agregado) só fique completo na frente R.

Em isolamento, o usuário pode listar sessões IDE com flag explícita ou
configurando `[sources].default = "ide"` no config.

## Pré-condições

- ✅ Frente P mergeada na `main` (commit `2375b41`)
- ✅ Material observacional coletado em 2026-05-27: 14 executions reais (chat / do múltiplas variantes / spec-dispatch / spec-generation / running) cobrindo todos os workflow_types e action_types previstos
- ✅ Schema observado documentado nas decisões #4-#10 abaixo
- ✅ Esforço revisado para baixo após coleta: 6-7h (era 8-10h)

## Decisões consolidadas (revisadas após coleta — 2026-05-27)

> **Nota:** estas decisões refletem o schema **observado** em 14 executions
> reais coletadas em 2026-05-27 (1 chat, 6 do, 4 spec-dispatch, 3
> spec-generation, 1 spec-generation running). O schema pré-coleta
> (commit anterior) tinha imprecisões corrigidas aqui.

1. **Identidade composta** `ide:<sessionId>` — slug fixo, sessionId UUID nativo do IDE

2. **Workspace path codificado em base64url** com padding por `=` substituído por `_`. Decoder espelha o encoder:
   - `L2hvbWUvbWVuemFuaS9EZXNlbnZvbHZpbWVudG8vbWVuY29kaW5nL2N2YXQtYWRlcHR1cw__` → `/home/menzani/Desenvolvimento/mencoding/cvat-adeptus`

3. **`profile_hash` é opaque** para o kiro-dash. Detectado pela presença do arquivo `f62de366d0006e17ea00a01f6624aabf` (catálogo de executions) dentro de `kiro.kiroagent/<hash>/`. Pode haver múltiplos profile_hash se usuário trocou de conta — todos são lidos. Há também um symlink `kiro.kiroagent/default/f62de366d0006e17ea00a01f6624aabf` apontando para o profile ativo (44B vs 402B no real).

4. **`workflowType` é BIPARTITE, não tripartite:**
   ```
   workflowType ∈ {chat-agent, spec-generation}
   ```
   A distinção real entre chat/do/spec acontece em **dois níveis combinados**:

   | Cenário | `workflowType` | `intent.classification` | comportamento |
   |---|---|---|---|
   | Pergunta simples | `chat-agent` | `chat` | model + say |
   | Autopilot executa | `chat-agent` | `do` | model + tools (read/write/bash) |
   | Pedido de spec (light) | `chat-agent` | `spec` | model + `specAgent` action |
   | Geração da spec (pesada) | `spec-generation` | (ausente — sub-execução) | invokeSubAgent + write/create + search |

   Pedido de spec dispara **2 executions encadeadas**: primeiro `chat-agent intent=spec` (orçamento baixo, ~0.008 cr) que invoca specAgent, depois `spec-generation` (orçamento alto, ~0.5-4 cr) que de fato gera os arquivos.

5. **Mapping para tipo interno:**
   - `Session` (kiro-dash) ← `<sessionId>.json` (IDE)
   - `Turn` (kiro-dash) ← cada `<execution>` cujo `chatSessionId == session.sessionId`. **Não pareamos history[i]/history[i+1]** — a `history[]` da sessão é só o registro UI, com mensagens do usuário; cada turno completo (input + processamento + output) é uma execution. As executions `spec-generation` ficam linkadas à execution `chat-agent intent=spec` que a disparou (mesmo `chatSessionId`); na visão de Turn, somar créditos de ambas como UM turn lógico (`spec`)
   - `ToolCall` ← derivado de **`usageSummary[].usedTools[]`** (fonte autoritativa de tool name). O `actions[]` array é detalhe de execução; cada fase de `model` do `usageSummary` corresponde a 1 LLM call que pode ter invocado tools listados em `usedTools`. Para um ToolCall granular (1 entrada por tool), iterar fases não-vazias de `usedTools`. Para overview, somar `usage` por `usedTools[i]` agregado

6. **Vocabulário de `actionType` (consolidado de 14 executions reais):**

   | Categoria | actionTypes |
   |---|---|
   | Universais | `intentClassification`, `model`, `say` |
   | Leitura | `readFile`, `readFiles`, `search` |
   | Escrita/edição | `create`, `write`, `replace` |
   | Execução shell | `runCommand`, `controlProcess`, `getProcessOutput` |
   | Diagnóstico | `getDiagnostics` |
   | Sub-agents | `invokeSubAgent`, `subagent_response` |
   | Spec-only | `specAgent`, `userInput` |

7. **Tool names normalizados** (fonte autoritativa = `usageSummary[].usedTools[]`):
   ```
   read_file, read_files, file_search, grep_search, list_directory
   fs_write, str_replace
   execute_bash, control_bash_process, get_process_output
   getDiagnostics
   invoke_sub_agent, subagent_response, report_progress
   ```

   Mapeamento `actionType → toolName` (não-óbvio, vem de campo):

   | actionType | toolName(s) emitidos |
   |---|---|
   | `readFile` | `read_file` |
   | `readFiles` | `read_files` (e/ou `read_file` ao agregar) |
   | `search` | `file_search`, `grep_search`, `list_directory` |
   | `create` | `fs_write` |
   | `write` | `fs_write` |
   | `replace` | `str_replace` |
   | `runCommand` | `execute_bash` |
   | `controlProcess` | `control_bash_process` |
   | `getProcessOutput` | `get_process_output` |
   | `getDiagnostics` | `getDiagnostics` |
   | `invokeSubAgent` | `invoke_sub_agent` |
   | `subagent_response` | `subagent_response` |

8. **Agent normalizado:** todas sessões IDE têm `agent = "kiro-ide"` no domínio interno. Variabilidade fica em campos novos `Turn.metadata`:
   - `workflow_type`: `chat-agent` ou `spec-generation`
   - `intent`: `chat`, `do`, `spec`, ou `None` (em spec-generation sub-execução)

9. **Modelo:** `selectedModel` quando explícito (`auto`, modelo nomeado), ou `defaultModelTitle` (`Agent`) como fallback. Quando `selectedModel == "auto"`, marcar como `kiro:auto` no domínio interno

10. **Sessão "live":** **alguma execution da sessão tem `status == "running"`** no catálogo de executions. Indicador: `endTime: 0` produz `dur` negativa absurda quando computada. **Esta é a heurística primária** — substitui o esquema `active + mtime` originalmente proposto. Métricas de `mtime`/`active` viram fallback quando catálogo não traz status, mas com o catálogo isso raramente é necessário.

11. **Project label:** workspace path do IDE entra na heurística existente de `project.py`; mesma regra de `cwd` do CLI

## Tasks (ordem TDD)

### T1 — Fixtures redatadas (a partir do material real coletado em 2026-05-27)

Base: 14 executions reais + 1 sessão real (`8e2c534f-0296-4bc8-9048-196ca3521378`, workspace `cvat-adeptus`). Conteúdo de mensagens **redatado** com placeholders curtos; mantém schema, IDs sintéticos.

- `tests/fixtures/ide/sessions/<uuid>_clean.json` — sessão "Clean State" minimalista
- `tests/fixtures/ide/sessions/sessions_index.json` — catálogo workspace
- `tests/fixtures/ide/executions/<exec>_chat.json` — chat-agent intent=chat (3 actions, ~0.094 cr)
- `tests/fixtures/ide/executions/<exec>_do_simple.json` — chat-agent intent=do, tools=[execute_bash] (~0.146 cr)
- `tests/fixtures/ide/executions/<exec>_do_complex.json` — chat-agent intent=do com process control (read+bash+control+getoutput, ~0.66 cr, 18 actions)
- `tests/fixtures/ide/executions/<exec>_do_write.json` — chat-agent intent=do com fs_write+str_replace+getDiagnostics (~2.65 cr, 30 actions)
- `tests/fixtures/ide/executions/<exec>_spec_dispatch.json` — chat-agent intent=spec (4 actions: intentClassification + model + specAgent + userInput, ~0.008 cr)
- `tests/fixtures/ide/executions/<exec>_spec_generation.json` — workflow=spec-generation, 84 actions, com invokeSubAgent + subagent_response + create + write (~4.26 cr)
- `tests/fixtures/ide/executions/<exec>_running.json` — workflow=spec-generation, status=running, endTime=0 (sessão live)
- `tests/fixtures/ide/executions/executions_index.json` — catálogo com mistura succeed/aborted/running
- `tests/fixtures/ide/build_ide_layout.py` — monta árvore filesystem completa em `tmp_path`, suportando 1+ profile_hash, 1+ workspace, n executions

**Privacidade:** redatar `actions[].input.content`, `actions[].output.content`, `actions[].say.content`, `actions[].userInput.content`, `history[].message`, `history[].editorState`, `history[].contextItems[].content`. Manter: IDs, timestamps, status, workflowType, intent.classification, actionType, actionState, usageSummary, contextUsagePercentage, autonomyMode, selectedModel.

**Commit:** `test(fixtures): layout completo Kiro IDE redatado (14 execs reais)`

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
  - **`workflow_type` ∈ {`chat-agent`, `spec-generation`}** — bipartite (decisão #4)
  - `start_time`, `end_time`, `status` ∈ {`succeed`, `failed`, `aborted`, `running`}
  - `actions: list[IdeAction]` — typed por actionType (vocabulário em decisão #6)
  - `usage_summary: list[IdeUsageEntry]` — `usage`, `unit`, `unit_plural`, **`used_tools: list[str]`** quando presente
  - `intent_result: Optional[IdeIntent]` quando há `intentClassification` em actions; `intent.classification ∈ {chat, do, spec}`. **Ausente em workflow=spec-generation** (sub-execução não passa por classifier)
  - `context_usage_percentage: float`
  - `autonomy_mode: str` — `Autopilot` ou outro modo futuro
- **Tests:** parsing de cada uma das 7 fixtures + ausência graciosa de campos opcionais (`intent_result is None` em spec-generation)
- **Commit:** `feat(ide-sessions): typed reader de execution com actions/usage/intent`

### T7 — Mapper IDE → tipo interno do kiro-dash

- `src/kiro_dash/backends/ide_mapper.py`
- `to_session(ide_session, executions_for_session) -> Session` (tipo interno)
- `to_turn(execution) -> Turn` — **uma execution = 1 turn**:
  - Créditos do turn: `sum(u.usage for u in execution.usage_summary)`
  - Modelo: `selectedModel` (ou `kiro:auto` se "auto") da sessão; modelo efetivo por fase fica em metadata
  - `metadata["workflow_type"]` = `chat-agent` ou `spec-generation`
  - `metadata["intent"]` = `chat`, `do`, `spec`, ou `None`
  - `metadata["actions_count"]` = `len(execution.actions)`
  - `metadata["used_tools"]` = união de `usage_summary[].usedTools[]`
  - **Spec lógico:** quando `intent=spec`, considerar a execution `spec-generation` linkada (mesmo `chatSessionId`, dispara em sequência) e somar créditos das duas em UM turn lógico. Default: turn = execution; flag `--split-spec-subexec` mostra as duas.
- `to_tool_calls(execution) -> list[ToolCall]`:
  - **Fonte autoritativa: `usageSummary[].usedTools[]`** (não `actionType == "tool"` — esse não existe; o vocabulário real é o de decisão #6)
  - Cada fase do `usage_summary` que tenha `usedTools` não-vazio gera 1 ToolCall por tool, com créditos atribuídos proporcionalmente (split simples se múltiplos tools na mesma fase)
  - `actionType == "intentClassification"` é metadata da execution, **não** vira ToolCall
- **Tests:** roundtrip de cada cenário das 7 fixtures (chat, do_simple, do_complex, do_write, spec_dispatch, spec_generation, running)
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

### T9 — Detecção de sessão live via catálogo de executions

- Heurística primária em `running_sessions()`:
  - Ler catálogo `f62de366d0006e17ea00a01f6624aabf` de cada profile_hash
  - **Sessão live ⇔ existe execution com `chatSessionId == session.id` E `status == "running"`** (decisão #10)
  - Indicador secundário (validação): `endTime: 0` na execution running
- Fallback (catálogo ausente ou execution running antiga abandonada >24h):
  - `session.active == True` E `mtime > now - threshold` → live (apenas best-effort, log warning)
- Threshold do fallback configurável `[ide_sessions].live_threshold_seconds = 60`
- **Tests:**
  - Catálogo com 1 execution running → live ✓
  - Catálogo só com succeed → não-live
  - Catálogo com running antiga (>24h) → fallback dispara
  - Catálogo ausente → fallback puro
  - Multiple sessions na mesma workspace, só uma com running → só ela live
- **Commit:** `feat(ide-sessions): heurística live via execution.status=running`

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

- `sessions/sessions_index.json` — catálogo workspace
- `sessions/<uuid>_clean.json` — sessão "Clean State"
- `executions/executions_index.json` — catálogo (succeed/aborted/running)
- `executions/<exec>_chat.json` — chat-agent intent=chat (3 actions)
- `executions/<exec>_do_simple.json` — chat-agent intent=do tools=[execute_bash]
- `executions/<exec>_do_complex.json` — chat-agent intent=do (read+bash+control+getoutput, 18 actions)
- `executions/<exec>_do_write.json` — chat-agent intent=do (fs_write+str_replace+getDiagnostics, 30 actions)
- `executions/<exec>_spec_dispatch.json` — chat-agent intent=spec (specAgent+userInput, 4 actions)
- `executions/<exec>_spec_generation.json` — workflow=spec-generation com invokeSubAgent (84 actions)
- `executions/<exec>_running.json` — workflow=spec-generation status=running endTime=0
- `build_ide_layout.py` — monta árvore filesystem em `tmp_path`, suporta múltiplos profile_hash, múltiplos workspaces, n executions

## Critérios de aceitação

- [ ] `pytest tests/ -v` 100% verde (~370+ testes — 301 atuais + ~70 novos)
- [ ] `kiro-dash recent --source ide` lista sessões IDE
- [ ] `kiro-dash recent --source all` concatena CLI+IDE com coluna source
- [ ] `kiro-dash session <prefix>` resolve prefix em ambas fontes; ambíguo → pede desambiguação com slug
- [ ] `kiro-dash today --source ide` agrega só IDE
- [ ] `kiro-dash audit running --source all` lista sessões live de ambas fontes (heurística IDE via `execution.status=running`)
- [ ] `kiro-dash whoami` mostra IDE sessions com contagem
- [ ] MCP tools aceitam `source` parameter
- [ ] Sem regressão nos comandos sem `--source` (default `cli` preserva comportamento)
- [ ] Documentação README atualizada com tabela de equivalências
- [ ] Fixtures cobertas com 7 cenários (chat, do_simple, do_complex, do_write, spec_dispatch, spec_generation, running)
- [ ] Spec lógico (chat-agent intent=spec + spec-generation) consolidado como 1 turn por default; `--split-spec-subexec` mostra os dois separados

## Pendências fora desta frente

- Dedup CLI ∩ IDE em `--source all` — frente R
- Aggregator multi-source nas queries históricas (`month`, `year`, `compare`) — frente R
- Snapshots schema bump — frente R
- Sync (rclone) cobrindo workspace-sessions IDE — frente R
- TUI ganha filtro source — frente R
- Banner "Kiro IDE detectado" para usuário que tinha só CLI — pode entrar aqui (extra) ou em R
