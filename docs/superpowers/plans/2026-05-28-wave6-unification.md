# Wave 6 / Frente R — Unificação CLI+IDE em queries

**Branch:** `feat/wave6-unification`
**Esforço:** 5-6h
**Depende de:** P + Q
**Entrega:** somatório/dedup multi-source em todos comandos, snapshots em schema v2, sync cobrindo IDE, TUI com filtro source. Bump v0.7.0.

## Objetivo

Fechar a Wave 6: o usuário com CLI **e** IDE instalados vê dados
**unificados** sem precisar especificar `--source all` toda vez. Default
muda de `cli` para `all`. Snapshots persistem o slug por sessão.
Cross-device via rclone reflete IDE também.

## Pré-condições

- Frentes P e Q mergeadas em `main`
- Cobertura de testes de P+Q em verde
- Working tree limpo, branch nova a partir de `main`

## Decisões consolidadas (revisar antes de codar)

1. **Default mudará de `cli` para `all`.** Quebra leve de comportamento — usuários CLI-only não notam (sem IDE → única fonte é CLI). Documentar em CHANGELOG e README
2. **Dedup por `internal_session_id`** — slug + UUID. Colisão real entre slugs distintos é impossível por design; colisão dentro do mesmo slug não acontece (UUIDs únicos por gerador)
3. **Snapshots v2:** schema bump com `schema_version: 2`, `internal_session_id` e `source` por sessão. Reader v0.7.0 lê v1 transparente (injeta `cli:` retroativo). Reader v0.6.x ignora campos extras (forward-compat JSON ok)
4. **Sync via rclone:** continua cobrindo só `.json` (metadata). Para IDE adicionamos `~/.config/Kiro/User/globalStorage/kiro.kiroagent/workspace-sessions/**/*.json` e o `state.vscdb` lido como JSON exportado (não copiar o sqlite — exportar `kiro.kiroAgent` em JSON antes do push). Decisão: **não sincar `state.vscdb`** porque billing é per-machine view e cada device tem seu refresh; sincar **só sessões IDE**
5. **TUI:** novo seletor de source (atalho `s`) cicla entre `all`/`cli`/`ide` no topo da tela. Estado salvo em config
6. **`audit running`/`stuck`:** aceita `--source` mas com nota: heurística IDE não tem lockfile, então estimativa é melhor-esforço

## Tasks (ordem TDD)

### T1 — `Aggregator` aceita lista de backends

- Refatorar `aggregator.py` para receber `backends: list[Backend]` em vez de instanciar `parser` diretamente
- Métodos como `today_summary`, `projects_summary`, `models_summary` chamam `backend.list_sessions()` em todos backends e fundem antes de agregar
- Dedup por `internal_session_id`:
  - Se duas sessões têm o mesmo `internal_session_id` (não deveria, mas defensivo) → log `SOURCE_DEDUP_AMBIGUOUS` e mantém a primeira na ordem de prioridade
- Ordenação respeita `[sources].priority` no config (default `["cli", "ide"]`)
- **Tests:** dedup edge cases, prioridade configurada, fontes vazias
- **Commit:** `refactor(aggregator): aceitar lista de Backend e deduplicar por internal_session_id`

### T2 — Snapshots v2 — schema + writer + reader migration

- Em `snapshots.py`:
  - `write_snapshot(date, host, sessions)` agora produz v2:
    ```json
    {
      "schema_version": 2,
      "host": "predator-ph315-54",
      "date": "2026-05-28",
      "sessions": [
        {"internal_session_id": "cli:8e2c534f-...", "source": "cli", ...},
        {"internal_session_id": "ide:abc...", "source": "ide", ...}
      ]
    }
    ```
  - `read_snapshot(path)` detecta `schema_version`:
    - Ausente ou `< 2` → v1 → injeta `source: "cli"` e `internal_session_id: "cli:<uuid>"` em memória
    - `2` → carrega direto
    - `> 2` → erro `SNAPSHOT_SCHEMA_DOWNGRADE` com hint para upgrade do kiro-dash
- **Tests:** roundtrip v1→v2 transparente, fixture v1, fixture v2, fixture v3 (erro)
- **Commit:** `feat(snapshots): schema v2 com internal_session_id + source; migração v1→v2 on-load`

### T3 — Lazy generation lê todas fontes

- Em `history.py` e `snapshots.py` o gerador lazy de snapshot do dia X lia só CLI; agora itera todos backends disponíveis no momento da consulta
- Para dia muito antigo (pré-instalação kiro-dash, mas IDE tem dados): gera snapshot v2 com sessões IDE descobertas
- Performance: limitar concorrência se um workspace IDE tem muitas sessões (default sequencial; paralelizável em Wave 7+)
- **Tests:** dia com só CLI, só IDE, ambos, nenhum
- **Commit:** `feat(history): lazy generation lê todos backends disponíveis`

### T4 — Self-healing 30d cobre IDE

- `snapshots.heal_recent(days=30)` agora itera todos backends ao detectar buracos
- Idempotente (não re-cria snapshot existente)
- **Tests:** healing com fontes mistas, healing após adição de IDE
- **Commit:** `feat(snapshots): self-healing 30d cobre todas fontes ativas`

### T5 — Default `--source` muda para `all`

- Em `cli.py`, defaults dos comandos passam de `cli` para `all`
- Usuário CLI-only: comportamento inalterado (única fonte é cli)
- Usuário com ambos: comportamento muda — agora vê tudo por padrão
- Adicionar nota visível em `today` da primeira execução pós-upgrade quando ambos backends disponíveis (1x):
  ```
  ℹ️  kiro-dash 0.7.0 agora une CLI + IDE por padrão. Use --source cli para comportamento anterior.
  ```
- **Tests:** ambos defaults, suprimir nota
- **Commit:** `feat(cli): default --source=all + nota de upgrade`

### T6 — Sync cobre sessões IDE

- `sync.py`:
  - Adicionar paths IDE ao manifest do rclone: `~/.config/Kiro/User/globalStorage/kiro.kiroagent/workspace-sessions/**/*.json`
  - Filtrar conteúdo de mensagem? **Não** — esses JSONs JÁ contêm `text/content/message` em mensagens. **DECISÃO:** sync **NÃO** inclui session.json de IDE por enquanto, **só catálogo `sessions.json`** + execution metadata (sem campos de mensagem)
  - Logo, o sync IDE é **mais limitado** que CLI (que sincava `.json` de metadata sem `.jsonl` de transcripts) — IDE precisa filtrar campos antes do upload
- Helper `redact_for_sync(session_json)` remove campos sensíveis antes do push
- **Tests:** redação verificada em fixture, push só de campos seguros
- **Commit:** `feat(sync): cobre sessões IDE com redação de mensagens antes do push`

### T7 — TUI: filtro de source no topo

- `views/app.py` adiciona seletor visível: `Source: [all] cli ide` no header
- Atalho `s` cicla entre os 3 modos
- Estado salvo em `config.toml` `[tui].default_source`
- Aplicado a todas abas que listam sessões
- **Tests:** smoke da TUI com cada source
- **Commit:** `feat(tui): seletor source no header com atalho s`

### T8 — TUI: badge de frescor no header

- Quando `IdeStateBackend` disponível, header mostra:
  ```
  Saldo: 1598/10000 (15.99%)  [verde · 47s atrás]
  ```
- Cor da badge segue freshness; aba Now ganha card dedicado com detalhes (overage, reset date)
- **Tests:** rendering com freshness levels variados
- **Commit:** `feat(tui): badge de saldo + frescor no header e card no Now`

### T9 — README final + matriz de fallback

- Seção `Suporte multi-source` no README com tabela:
  ```
  CLI | IDE | Comportamento
  ----+-----+--------------
   ✓  |  ✓  | Modo completo: CLI + IDE somados, billing autoritativo, dedup interno
   ✓  |  ✗  | Modo CLI-only: estimativa de saldo, banner sugerindo IDE
   ✗  |  ✓  | Modo IDE-only: billing autoritativo, sem audit running confiável
   ✗  |  ✗  | Onboarding: hint para instalar Kiro CLI
  ```
- Atualizar diagrama de stack com `IdeStateBackend` + `IdeSessionBackend`
- Atualizar lista de tools MCP
- Documentar nova tabela de configuração consolidada (apontando para os planos)
- **Commit:** `docs: README — suporte multi-source CLI + IDE`

### T10 — CHANGELOG.md (criar se não existir)

- Convenção Keep a Changelog
- Entrada `[0.7.0] - 2026-05-28`:
  - Added: IdeStateBackend, IdeSessionBackend, sources.py, snapshots v2, --source flag, badge frescor, banner IDE
  - Changed: default --source de `cli` para `all`; balance e plan get auto-detect via IDE
  - Documentation: ADR-0001, plano Wave 6
- **Commit:** `docs: CHANGELOG 0.7.0`

### T11 — Bump versão + tag

- Atualizar `pyproject.toml`: `0.6.1` → `0.7.0`
- Atualizar badge no README
- Tag `v0.7.0`
- **Commit:** `chore: bump v0.7.0`

## Configuração (escopo da frente R)

### Variáveis de ambiente

| Var | Default | Propósito |
|---|---|---|
| `KIRO_DASH_DEFAULT_SOURCE` | `all` | source padrão |

### CLI flags

Já introduzidas em Q. R apenas muda defaults e adiciona nota de upgrade.

### Config (`~/.config/kiro-dash/config.toml`)

```toml
[sources]
priority = ["cli", "ide"]   # ordem em dedup
default = "all"             # source default

[tui]
default_source = "all"      # source default na TUI

[sync]
include_ide_sessions = true   # sincar sessões IDE com redação?
```

### Códigos de erro

| Código | Onde | Significado |
|---|---|---|
| `SOURCE_DEDUP_AMBIGUOUS` | `aggregator` | mesmo `internal_session_id` em duas leituras (não deveria) |
| `SNAPSHOT_SCHEMA_DOWNGRADE` | `read_snapshot` com `schema_version > 2` | upgrade do kiro-dash necessário |
| `SYNC_IDE_REDACTION_FAIL` | redator não conseguiu remover campo sensível | aborta push do arquivo |

## Schema fixtures

Adições em `tests/fixtures/`:

- `snapshots/v1_legacy.json` — snapshot v1 sem slug
- `snapshots/v2_pure_cli.json` — v2 só CLI
- `snapshots/v2_pure_ide.json` — v2 só IDE
- `snapshots/v2_mixed.json` — v2 com ambas fontes
- `snapshots/v3_future.json` — schema_version=3 para testar erro
- `sync/redacted_session_ide.json` — saída esperada do redator

## Critérios de aceitação

- [ ] `pytest tests/ -v` 100% verde
- [ ] `kiro-dash today` (sem flag) une CLI + IDE quando ambos disponíveis
- [ ] `kiro-dash today --source cli` reproduz comportamento da v0.6.x
- [ ] `kiro-dash session <prefix>` resolve prefix em ambas fontes; ambíguo pede desambiguação
- [ ] Snapshot v1 antigo é lido transparente como v2 em memória
- [ ] Snapshot v2 escrito tem `schema_version`, `internal_session_id`, `source` por sessão
- [ ] Self-healing detecta buracos e gera snapshots v2 cobrindo IDE
- [ ] Lazy generation de dia distante reconstrói com sessões IDE históricas
- [ ] `kiro-dash sync push` envia sessões IDE redatadas, sem campos `text`/`content`/`message`
- [ ] TUI mostra seletor source no header, badge de saldo+frescor
- [ ] README e CHANGELOG atualizados
- [ ] `pyproject.toml` em `0.7.0`, tag `v0.7.0` aplicada local
- [ ] `pipx install --force ~/Desenvolvimento/mencoding/kiro-dash` mantém binários funcionando
- [ ] Nota de upgrade aparece 1x na primeira execução com ambos backends, suprimida depois

## Release checklist (final da Wave 6)

1. Merge das 3 frentes na `main` em ordem (P → Q → R)
2. Verificação manual:
   - [ ] `kiro-dash whoami` lista todas fontes ativas
   - [ ] `kiro-dash balance` exibe saldo do IDE com frescor
   - [ ] `kiro-dash today` agrega CLI + IDE
   - [ ] `kiro-dash recent --source all --show-source` lista com coluna source
   - [ ] `kiro-dash audit running --source all` lista live de ambas fontes
   - [ ] `kiro-dash tui` abre, navega abas, seletor source funciona
3. Push para `origin/main` + tag `v0.7.0`
4. Bump local com `pipx install --force ~/Desenvolvimento/mencoding/kiro-dash`
5. Atualizar memória `~/iris/memory/project_kiro_dash.md` (ou criar) com estado pós-Wave 6
6. Decisão sobre próxima wave (Wave 7 — pendências listadas no overview)

## Pendências fora desta wave

Listadas no [`overview`](2026-05-28-wave6-overview.md#pendências-fora-da-wave-6-wave-7).
