# Changelog

Todas as mudanças notáveis neste projeto serão documentadas aqui.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
e o projeto adere a [Semantic Versioning](https://semver.org/lang/pt-BR/).

## [0.8.0] - 2026-05-27

Wave 10 — suporte a Windows 11 (TUI + MCP). Minor bump por
introdução de feature transversal.

### Adicionado

- **Cross-platform paths (T1-W10)** —
  `src/kiro_dash/_platform_paths.py` com 8 helpers que resolvem
  paths corretos por OS:
  - Linux: `$XDG_CONFIG_HOME` ou `~/.config/`,
    `$XDG_DATA_HOME` ou `~/.local/share/`
  - Windows: `%APPDATA%` (Roaming) e `%LOCALAPPDATA%` (Local)
  - macOS: `~/Library/Application Support/`
  Helpers cobrem Kiro IDE storage, kiro-cli sessions e
  kiro-dash own dirs. Env vars de override
  (`KIRO_DASH_IDE_SESSIONS_ROOT`, `KIRO_DASH_CONFIG_DIR`,
  `KIRO_DASH_DATA_DIR`) preservados.
- **Script PowerShell de instalação (T3-W10)** —
  `scripts/install.ps1` com 5 steps idempotentes: detecta
  Python 3.10+ (winget instala Python 3.13 se ausente),
  instala pipx --user, adiciona Scripts/ ao PATH user, instala
  kiro-dash via pipx, verifica e imprime instruções MCP.
  Parâmetros: `-Version <tag>`, `-Force`, `-Local`.
  One-liner: `iwr -useb <url>/scripts/install.ps1 | iex`.
- **Documentação Windows no README (T4+T5-W10)** — seção
  "Windows 11" com tabela de paths por OS, exemplo de
  configuração MCP em `%USERPROFILE%\.kiro\agents` (Win) e
  `~/.kiro/agents` (Linux), env vars de override.
- **31 testes parametrizados por OS** —
  `tests/test_platform_paths.py` cobre Linux/Windows/macOS
  via mock de `sys.platform`. Garante divergência de paths e
  igualdade do dotfile dir (`~/.kiro/`).

### Modificado

- 5 pontos hardcoded refatorados para usar `_platform_paths`:
  `ide_state.DEFAULT_IDE_STATE_VSCDB`,
  `ide_sessions.DEFAULT_IDE_SESSIONS_ROOT`,
  `parser.DEFAULT_SESSIONS_DIR`, `config.default_config_path`,
  `snapshots.snapshots_dir_default`.

### Diferido para Wave 11 (futuro)

- Atalho de Start Menu via PowerShell (após validar UX em Win11).
- Validação E2E em máquina Windows real (atualmente só via
  mock de `sys.platform`).
- Suporte a binário standalone (.exe via PyInstaller).

## [0.7.3] - 2026-05-27

Wave 9 — bug fix crítico de leitura de executions IDE.

### Corrigido

- **`IdeSessionBackend` ignorava executions com filename hex32
  (T1-W9)** — a regex `_EXECUTION_ID_RE` esperava nome de arquivo
  em formato UUID (8-4-4-4-12 com hífens), mas o Kiro IDE atual
  salva blobs com nomes de 32 hex chars sem hífens (storage-key
  opaca, NÃO é hash do executionId). O `executionId` dentro do
  JSON segue UUID; só o filename mudou.

  Sintoma: `kiro-dash whoami` mostrava `ide-sessions ✓ (N
  workspaces)` mas `today`/`tools`/`recent` não viam turns IDE
  (`list_sessions` retornava sessões com 0 turns / 0 créditos).

  Fix: regex aceita ambos formatos (UUID com hífens OU 32-hex sem
  hífens). `read_execution()` continua sendo autoridade semântica
  (filename é só pré-filtro de I/O).

  Ver [ADR-0002](docs/adr/0002-execution-blob-filename-opaque.md).

### Adicionado

- `tests/test_ide_filename_regex.py` (T2-W9) — 20 testes
  regressivos: 6 filenames válidos parametrizados, 9 inválidos,
  3 integration tests com fixtures de layout completo
  (hex32-only, UUID-only, mix de auxiliares), 1 teste defensivo
  contra blobs JSON inválidos.
- `docs/adr/0002-execution-blob-filename-opaque.md` (T3-W9) —
  documenta o finding, alternativas consideradas, sinais de
  erosão futura.

### Modificado

- `tests/test_plan_command.py` e `tests/test_tools_command.py`
  agora isolam do storage IDE real do dev via
  `KIRO_DASH_NO_IDE_SESSIONS` + `KIRO_DASH_NO_IDE_STATE` no
  monkeypatch. Antes do fix da regex, esses testes passavam por
  sorte (IDE retornava 0); agora que IDE funciona corretamente,
  o mock explícito é necessário.

## [0.7.2] - 2026-05-27

Hotfix de bug crítico em v0.7.1.

### Corrigido

- **Crash ao abrir help modal (T6-W8)** — `HelpModal` passava
  `header_style="bold"` para o `DataTable` da Textual, que não
  aceita esse keyword (era API do `rich.Table`). Causava
  `TypeError: DataTable.__init__() got an unexpected keyword
  argument 'header_style'` ao pressionar `?` na TUI. Movido
  estilo bold do header para `styles.tcss`
  (`#help-table > .datatable--header { text-style: bold; }`).
- Adicionados 4 testes regressivos em `test_help_modal.py`
  cobrindo mount, contagem de rows, dismiss via ESC e dismiss
  via `q`.

## [0.7.1] - 2026-05-28

Wave 8 — refinamentos visuais TUI/CLI. Sem mudanças de API
breaking; foco em UX e legibilidade.

### Adicionado

- **Filtro real por source nas tabs da TUI (T1-W8)** —
  `views.tabs._helpers.collect_for_tab` faz cada tab ler
  `self.app.current_source`. Tecla `s` agora filtra de fato as
  abas Now/Today/Projects/Models/Tools (antes era só estado
  visual). Headers mostram `source=X` quando ≠ all.
- **Card de saldo no Now tab (T2-W8)** —
  `_build_balance_card(sources)` renderiza saldo IDE com
  `bar_inline` (30 width), cor de pct (verde<80, amarelo 80-95,
  vermelho>95) E cor de freshness (verde<3h, amarelo 3-12h,
  vermelho 12-24h, cinza>24h). Card oculto se IDE indisponível
  ou state read falha.
- **Progress bar no `balance` CLI (T3-W8)** — barra wider (40
  cells) com tick line marcando posições 80% (yellow) e 95%
  (red), tick label mostrando 0% / 80% / 95% / 100%. IDE com
  overage>0 ganha barra dedicada de 20 cells em red.
- **`whoami` como tabela rich (T4-W8)** —
  `Sources.summary_rows()` retorna tuplas tipadas
  `(slug, symbol, color, detail)`. Painel "Fontes detectadas"
  vira tabela rich com colunas source/status/descrição.
  `summary_lines()` preservado para compat.
- **Esquema de cores TUI (T5-W8)** — `styles.tcss` reescrito
  com paleta consistente: tabs ativas com `$accent` + bold,
  headers das tabs com `$boost` background, balance card com
  border round primary, tools detail panel com border round
  accent.
- **Help modal completo (T6-W8)** — `HelpModal` Textual
  ModalScreen com tabela 11×3 (tecla / ação / contexto).
  `action_help` (`?`) abre via `push_screen`. ESC ou `q` fecha.
- **Empty states informativos (T7-W8)** — `recent`/`today`/
  `tools`/`session` mostram hints contextuais quando vazio
  (ex.: "Tente --source all" ou "Aumente --hours").
- **`aggregate_tools_in_window_by_source(source, ...)`** —
  dispatcher que escolhe entre `aggregate_tools_in_window` (CLI),
  `aggregate_tools_in_window_ide` ou `aggregate_tools_in_window_combined`.

### Modificado

- Tecla `s` na TUI agora **dispara refresh em todas as tabs**
  após cycle (`app._refresh_all_tabs()`).
- `_render_balance_from_local_estimate` consome via
  `collect_sessions("all")` em vez de `load_all_sessions()`.

### Diferido para Wave 9 (futuro)

- Filtro source persistente entre execuções (config
  `[tui].default_source`).
- Migração v1→v2 de snapshots reescrevendo arquivos no disco.
- Animação de transição ao trocar source na TUI.
- Theme dark/light alternável.

## [0.7.0] - 2026-05-28

Wave 6 — suporte multi-backend (Kiro CLI + Kiro IDE) consolidado.

### Adicionado

- **`IdeStateBackend`** — billing autoritativo do servidor lido
  do `state.vscdb` do Kiro IDE, com badge de frescor (verde <3h /
  amarelo 3-12h / vermelho 12-24h / cinza ≥24h).
- **`IdeSessionBackend`** — sessões IDE com 4 capabilities (SESSIONS,
  TURNS, TOOL_CALLS, RUNNING). Lê
  `~/.config/Kiro/User/globalStorage/kiro.kiroagent/` em modo
  read-only forte.
- **`Backend` ABC + `Capability` enum** em `src/kiro_dash/backends/`
  para suporte multi-source extensível.
- **`Sources` detector** (`sources.py`) com `detect()` autoenumera
  backends disponíveis e expõe `available_for(capability)`.
- **`workspace_codec`** — encode/decode base64url Kiro-compatible
  (padding trailing-only).
- **`ide_mapper`** — converte schema IDE para tipo interno
  (`Session`/`Turn`/`ToolCall`).
- **Helper `freshness`** compartilhado com 4 níveis (verde/amarelo/
  vermelho/cinza) e formatação de idade.
- **Banner de onboarding** sugerindo Kiro IDE quando só CLI detectado
  (1×/dia, suprimível por `KIRO_DASH_NO_BANNER=1`).
- **`collect_sessions(source, dedupe=True)`** central em
  `sources.py` para coleta multi-fonte com dedup por session_id.
- **MCP tool `usage_state`** — billing autoritativo via stdio.
- **Flag `--source cli|ide|all`** em `recent`, `audit running`,
  `session <prefix>` (com `auto` em `session`).
- **Flag `--show-source`** em `recent` força coluna source.
- **Param `source` em MCP tools** `active_sessions` e
  `session_details` (com `auto` em `session_details`).
- **Variáveis de ambiente:** `KIRO_DASH_IDE_STATE_PATH`,
  `KIRO_DASH_NO_IDE_STATE`, `KIRO_DASH_IDE_SESSIONS_ROOT`,
  `KIRO_DASH_NO_IDE_SESSIONS`, `KIRO_DASH_NO_BANNER`.

### Modificado

- **Default `--source` em comandos com flag mudou de `cli` para
  `all`.** Usuários CLI-only não notam (única fonte é CLI). Usuários
  com ambos backends agora veem dados unificados sem flag explícita.
  Para comportamento da v0.6.x: passe `--source cli`.
- **`kiro-dash balance`** virou dual-mode: lê billing autoritativo
  do IDE quando disponível (com badge de frescor); cai para
  estimativa local com flag `--no-ide` ou quando IDE indisponível.
- **`kiro-dash plan get`** auto-detecta `usageLimit`, `overageCap`,
  `overageRate`, `resetDate` do servidor via IDE quando disponível.
- **`kiro-dash whoami`** ganhou painel "Fontes detectadas" listando
  todas as fontes ativas com idade do snapshot e nível de frescor.
- **Snapshots v2 schema** — adiciona `internal_session_id` e `source`
  por sessão em `by_session`. Reader v0.7.0 lê v1 transparentemente
  (injeta `cli:` retroativo); v3+ levanta `SnapshotSchemaError`.
- **Lazy generation e self-healing 30d** agora cobrem todas as
  fontes ativas (consequência da nova coleta multi-source).

### Documentação

- **ADR-0001** — multi-backend architecture (CLI + IDE).
- **Plano Wave 6** em 4 arquivos (overview + frentes P, Q, R) em
  `docs/superpowers/plans/`.
- **README seção "Suporte multi-source"** com matriz CLI × IDE ×
  Comportamento.
- **README seção "Sessões do Kiro IDE"** com workflows observados
  (`chat-agent` × intent + `spec-generation`).
- **README seção "Saldo autoritativo via Kiro IDE"** com tabela de
  frescor.
- **README env vars consolidadas** em tabela única.

### Wave 7 — finalização das pendências (aplicado pré-release)

Após o code review da Wave 6, os 5 itens diferidos para "Wave 7"
foram implementados antes do tag final:

- **T1-W7**: tabela `_MODEL_RATE_MULTIPLIERS` em `ide_mapper.py`
  + função `rate_multiplier_for_model(model_id)` com match exato
  e por prefixo. Cobre Opus 4.7/4.5/4 (2.2/2.0), Sonnet 4.5/4/3.5
  (1.0), Haiku 4.5/4 (0.3). Aplicado em `to_session`.
- **T2-W7**: `consolidate_spec_executions(executions)` em
  `ide_mapper.py` é função opt-in (default fluxo permanece "1
  execution = 1 turn") que detecta padrão chat-agent intent=spec
  + spec-generation linkadas e funde em 1 IdeExecution lógico
  (preservando execution_id do dispatcher, somando créditos).
- **T3-W7**: comando `tools` agora cobre CLI **e** IDE.
  `aggregate_tools_in_window_combined` deduplica por nome somando
  counts. Tools IDE vêm de `usage_summary[].usedTools[]`.
  `KIRO_DASH_NO_IDE_SESSIONS=1` desabilita parcela IDE.
- **T4-W7**: módulo `sync_redactor.py` com redação pura
  (sem I/O, idempotente, deep-copy) de sessões IDE para sync seguro.
  `sync.sync_push_ide(cfg, ide_root)` cria temp dir staged +
  rclone copy + cleanup. Comando CLI `sync push --include-ide`.
  Vocabulário redatado: `history.message`, `editorState`,
  `actions.input.{content,fileText,command,oldStr,newStr,message}`,
  `actions.output.{content,message,output,response}`,
  `actions.rawInput`, `input.data.messages`, `context.messages`.
- **T5-W7 + T6-W7**: TUI ganhou binding `s` que cicla
  `current_source` ∈ {`all`, `cli`, `ide`} (estado visual com
  notify). `sub_title` do header mostra `source=X · saldo:
  cur/lim (pct%) [color · age]` quando IDE detectado. **Limitação**:
  tabs ainda lêem all por default em v0.7.0; filtro por aba é
  Wave 8.

### Diferido para Wave 8 (futuro)

- **Filtro real por source nas tabs da TUI** — T5-W7 hoje é só
  visual; tabs continuam lendo all default.
- **Migração v1→v2 de snapshots reescrevendo arquivos no disco**
  — atual é só in-memory.
- **TUI card dedicado de saldo no Now tab** — T6-W7 só fez
  subtitle.
- **Migração v1→v2 com `internal_session_id` em UUID truncado**
  — aceitável best-effort; lookups cross-version dão miss.

### Code review da Wave 6 (aplicado pré-release)

Antes do commit final, revisão completa da Wave 6 levantou
13 achados (3 blockers, 7 importantes, 3 polish). Resolvidos:

- **B1**: `today`/`projects`/`models` (CLI) e `tool_today_summary`/
  `tool_top_projects`/`tool_top_models` (MCP) agora usam
  `collect_sessions("all")` — agregados consistentes com promessa
  do default `--source=all`.
- **B2**: `_collect_sessions_for_mcp` removido (duplicação);
  `mcp_server` consome `sources.collect_sessions` direto.
- **B3**: `Sources.has_only_cli` agora exige
  `ide_state is None AND ide_sessions is None` — banner de
  onboarding não falsamente aparece para usuário com IDE detectado
  via sessions mas state.vscdb stale.
- **I1**: `IdeSessionBackend._exec_index_cache` evita re-scan de
  filesystem em chamadas múltiplas dentro da mesma instância
  (`list_sessions` + `iter_turns` + `iter_tool_calls`).
  `invalidate_cache()` para refresh explícito.
- **I2**: `Aggregate.source_session_id` (Optional, default None)
  elimina parsing reverso de `label` no escritor de snapshots v2.
- **I5**: `tool_session_details` description MCP documenta
  retorno `{"ambiguous": True, "matches": [...]}` em modo `auto`.
- **I6**: payload MCP de sessão IDE serializa
  `context_window_tokens: null` (placeholder interno 200000 não
  reflete servidor).
- **I7**: `_scan_all_executions` filtra arquivos por regex UUID,
  evitando tentar parsear arquivos auxiliares.
- **Polish**: `field` import órfão removido; docstring de `Sources`
  atualizado; `available_for(USAGE_STATE)` simplificado;
  `_cached_state` sentinel removido de `IdeStateBackend`.

## [0.6.1] - 2026-05-25

Versão pré-Wave 6 (single-source CLI). Mantida para referência
histórica do estado pré-multi-backend.
