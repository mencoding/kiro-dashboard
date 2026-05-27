# Wave 6 — Overview

**Data:** 2026-05-28
**Versão alvo:** v0.7.0
**Princípio:** suporte a múltiplas fontes Kiro (CLI + IDE) com isolamento por adapter.

Decisões fundadoras: [`ADR-0001 — Multi-backend architecture`](../../adr/0001-multi-backend-architecture.md).

## Frentes

| Frente | Plano | Branch | Esforço | Depende de |
|---|---|---|---|---|
| **P** — `IdeStateBackend` para billing | [`2026-05-28-wave6-ide-state.md`](2026-05-28-wave6-ide-state.md) | `feat/wave6-ide-state` | 4-5h | — |
| **Q** — `IdeSessionBackend` para sessões IDE | [`2026-05-28-wave6-ide-sessions.md`](2026-05-28-wave6-ide-sessions.md) | `feat/wave6-ide-sessions` | 8-10h | P |
| **R** — Unificação CLI+IDE em queries | [`2026-05-28-wave6-unification.md`](2026-05-28-wave6-unification.md) | `feat/wave6-unification` | 5-6h | P + Q |

Total: **17-21h em 3 ondas sequenciais.**

## Dependências

```
P (IdeStateBackend) ──┐
                      ↓
                Q (IdeSessionBackend) ──┐
                                        ↓
                                  R (Unificação) ──→ Wave 6 done (v0.7.0)
```

Sequencial obrigatório:

- Q precisa do `Backend` ABC e do `sources` detector criados em P
- R precisa do `IdeSessionBackend` de Q para fazer dedup multi-source

Não há onda paralela possível nesta wave porque cada frente toca o
`aggregator.py` e o `sources.py` em camadas que se sobrepõem.

## Ordem de execução

### Onda 1 — P sozinho (4-5h)

`IdeStateBackend` + `Backend` ABC + `sources.py` detector + comandos
`balance`/`plan get` lendo billing autoritativo + MCP tool `usage_state`.

Release intermediária possível: **v0.6.2** se houver demanda por entregar
billing autoritativo antes de Q estar pronto. Decisão fica para o final
de P.

### Onda 2 — Q sozinho (8-10h)

`IdeSessionBackend` lendo `workspace-sessions/` e arquivos de execution.
Normalizer schema IDE → tipo interno. CLI ganha coluna `source` em
listings. Em isolamento ainda — ainda não deduplicado com CLI.

### Onda 3 — R sozinho (5-6h)

Aggregator aceita N backends. Schema bump v1→v2 nos snapshots.
TUI ganha filtro `--source`. Sync via rclone cobre IDE.
Bump v0.7.0 + tag.

## Conflitos esperados (sequenciais, não paralelos)

| Arquivo | P | Q | R |
|---|---|---|---|
| `parser.py` | rename para `cli_json_backend.py` | — | — |
| `aggregator.py` | aceita Backend ABC | adiciona join IDE sessions ↔ executions | aceita N backends + dedup |
| `cli.py` | `balance`/`plan` consomem usage_state | nova coluna `source` em listings | flag `--source cli\|ide\|all` |
| `mcp_server.py` | tool `usage_state` | tools de sessão também olham IDE | dedup por internal_session_id |
| `snapshots.py` | — | escreve com `source` | bump schema v2 + migração on-load |
| `views/` (TUI) | — | — | filtro source + badge frescor |
| `README.md` | seção billing autoritativo | seção sessões multi-source | matriz de fallback |
| `tests/fixtures/ide/` | fixture de `state.vscdb` | fixtures de sessions/executions | fixtures cross-source |

Cada frente cria branch própria; merges em ordem fechada (P → Q → R)
direto na `main`.

## Decisões consolidadas (com Léo, em ADR-0001)

1. **Identidade composta** `<source_slug>:<session_id>` — slugs `cli`,
   `ide`, `cli-sqlite` (futuro)
2. **Política de frescor** com 4 faixas: verde <3h, amarelo 3-12h,
   vermelho 12-24h, cinza ≥24h
3. **Migração transparente** — sem comando dedicado, schema v1→v2
   acontece no carregamento; histórico longo via lazy on-demand
4. **Read-only forte** — todos backends abrem em modo leitura, sem
   tocar em paths de auth
5. **Privacidade preservada** — IDE traz mais campos (intent, actions),
   mas conteúdo de mensagens permanece fora de índice/cache/snapshot/MCP
6. **Banner de instalação IDE** quando só CLI detectado, com mensagem
   apontando para saldo autoritativo

## Configuração — visão consolidada

Cada frente adiciona seu próprio bloco. Visão agregada de tudo que
entra na Wave 6 em ambiente/CLI/config:

### Variáveis de ambiente

| Var | Default | Frente | Propósito |
|---|---|---|---|
| `KIRO_DASH_IDE_STATE_PATH` | auto | P | override do path do `state.vscdb` |
| `KIRO_DASH_NO_IDE_STATE` | unset | P | desabilita leitura do billing IDE |
| `KIRO_DASH_IDE_SESSIONS_ROOT` | auto | Q | override do `globalStorage/kiro.kiroagent/` |
| `KIRO_DASH_NO_IDE_SESSIONS` | unset | Q | desabilita leitura de sessões IDE |
| `KIRO_DASH_DEFAULT_SOURCE` | `all` | R | fonte padrão para comandos sem `--source` |

### CLI flags adicionadas

| Flag | Comandos | Frente | Propósito |
|---|---|---|---|
| `--no-ide` | `balance`, `plan get` | P | ignora billing IDE, força estimativa local |
| `--source cli\|ide\|all` | `today`, `projects`, `models`, `recent`, `tools`, `session`, `audit *` | R | filtra por fonte |
| `--show-source` | listings | Q | adiciona coluna `source` no output |

### Config (`~/.config/kiro-dash/config.toml`)

| Seção | Chave | Frente | Default | Propósito |
|---|---|---|---|---|
| `[sources]` | `priority` | R | `["cli", "ide"]` | ordem de preferência quando duas fornecem mesma capability |
| `[sources]` | `default` | R | `"all"` | mesmo que `KIRO_DASH_DEFAULT_SOURCE` |
| `[freshness]` | `green_max_hours` | P | `3` | limite verde |
| `[freshness]` | `yellow_max_hours` | P | `12` | limite amarelo |
| `[freshness]` | `red_max_hours` | P | `24` | limite vermelho |

### Códigos de erro (estrutura comum em todas frentes)

Prefixados por escopo. Renderizados em mensagens de CLI e em logs MCP.

| Código | Frente | Significado |
|---|---|---|
| `IDE_STATE_UNAVAILABLE` | P | `state.vscdb` ausente ou ilegível |
| `IDE_STATE_STALE` | P | data_age > red_max_hours; warning não fatal |
| `IDE_STATE_SCHEMA_UNKNOWN` | P | versão do schema do `kiro.kiroAgent` não testada |
| `IDE_WORKSPACE_DECODE_FAIL` | Q | nome de diretório base64url inválido em workspace-sessions |
| `IDE_EXECUTION_NOT_FOUND` | Q | `chatSessionId` da sessão não tem execution correspondente |
| `IDE_INTENT_PARSE_FAIL` | Q | campo `intentResult` ausente ou malformado |
| `SOURCE_DEDUP_AMBIGUOUS` | R | mesmo `internal_session_id` em duas leituras (não deveria acontecer) |
| `SNAPSHOT_SCHEMA_DOWNGRADE` | R | snapshot v2 lido por código que esperava v1 |

## Pendências fora da Wave 6 (Wave 7+)

- **`CliSqliteBackend` watchlist:** implementar quando o Kiro CLI
  começar a popular `conversations_v2` no sqlite. Adapter-shell já
  existe na ABC, só falta o reader concreto
- **`KIRO_DASH_ALLOW_CONTENT=1`:** opt-in para leitura de conteúdo de
  mensagens; desenho preliminar no ADR-0001, implementação fora desta wave
- **Kiro Web cache:** se o Kiro Web (browser) começar a expor cache
  local em `~/.config/Kiro-Web/` ou similar, virá novo backend
- **Auto-migração de schema_version:** v2→v3 quando houver; framework
  de migrações está sendo introduzido nesta wave para suportar v1→v2,
  mas formal de versionamento (semver de schema interno) fica para v0.8
- **Detecção de Kiro IDE no remoto via SSH** (kiro-dash-sync olhando
  storage IDE em outro device): explorar se faz sentido em multi-device
  workflow
- **Polling opt-in em outras abas da TUI** (item original da Wave 5
  overview, não absorvido na 6)
- **Compactação de snapshots > 1 ano** (gz)
