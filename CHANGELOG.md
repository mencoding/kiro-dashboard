# Changelog

Todas as mudanças notáveis neste projeto serão documentadas aqui.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
e o projeto adere a [Semantic Versioning](https://semver.org/lang/pt-BR/).

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

### Diferido para Wave 7

- **Sync rclone cobrindo IDE sessions** — implementação segura
  precisa redator de mensagens robusto.
- **TUI seletor de source** (atalho `s`) e **TUI badge de saldo
  no header**.
- **Comandos `tools` (transcript .jsonl) com flag `--source`** —
  esse caminho lê arquivos `.jsonl` do CLI; IDE expõe tools via
  `usage_summary[].usedTools[]` por outro caminho. Unificar é
  trabalho de Wave 7.
- **Consolidação spec lógica** (chat-agent intent=spec +
  spec-generation linkadas em 1 turn).
- **`rate_multiplier` por modelo IDE** — atualmente fixo em 1.0
  (tabela de mapping é refactor de Wave 7).
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
