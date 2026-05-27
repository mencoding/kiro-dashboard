# Wave 3 — Overview

**Data:** 2026-05-26
**Versão alvo:** v0.4.0
**Princípio:** 3 frentes 100% independentes, todas paralelas em uma única onda.

## Frentes

| Frente | Plano | Branch | Esforço | Depende de |
|---|---|---|---|---|
| **H** — Aliases + heurística completa + filtro `--agent` | [`2026-05-26-wave3-aliases-agent.md`](2026-05-26-wave3-aliases-agent.md) | `feat/wave3-aliases-agent` | 3-4h | — |
| **I** — Cache parser incremental | [`2026-05-26-wave3-cache.md`](2026-05-26-wave3-cache.md) | `feat/wave3-cache` | 4-5h | — |
| **J** — Audit/Watchdog + kill interativo | [`2026-05-26-wave3-audit.md`](2026-05-26-wave3-audit.md) | `feat/wave3-audit` | 5-6h | — |

Total: 12-15h. 1 sessão de execução paralela.

## Dependências

```
H ─┐
   │
I ─┼─→ Wave 3 done (v0.4.0)
   │
J ─┘
```

Sem dependências cruzadas. Cada frente toca arquivos quase disjuntos:

- **H** mexe em `config.py`, `project.py`, `aggregator.py`, `cli.py`
- **I** mexe em `parser.py`, `jsonl_parser.py`, `cli.py` (subgrupo `cache`); **cria** `cache.py`
- **J** mexe em `models.py`, `parser.py`, `cli.py` (subgrupo `audit`); **cria** `watchdog.py`

## Conflitos esperados (todos triviais)

- **`cli.py`** — H adiciona subgrupo `aliases`, I adiciona `cache`, J adiciona `audit`. Pure adições no fim do arquivo. Resolução: aceitar todas.
- **`parser.py`** — I adiciona hook de cache em `load_session_file`; J adiciona `read_lock`. Funções diferentes; conflito de adição em imports/topo se ocorrer.
- **`README.md`** — todas as 3 frentes adicionam seções. Conflito de adição.

## Onda única — paralelo total

| Worktree | Frente |
|---|---|
| `.worktrees/wave3-aliases-agent` | **H** |
| `.worktrees/wave3-cache` | **I** |
| `.worktrees/wave3-audit` | **J** |

Após terminarem: merge sequencial H → I → J. Bump `v0.4.0`. Tag.

## Decisões consolidadas (registradas com Léo)

- **Sem AWS auto-detect** — API privada, fica adiada para Wave 4+ (ou nunca, depende da estabilidade).
- **Sem launcher** — TUI atual já cumpre a função quando aberta em terminal separado.
- **Audit sem root, sem hook** — reusa `.json`/`.lock` nativos. PostToolUse via hook é redundante (o `.jsonl` já é log nativo).
- **Kill interativo** — `audit kill` pergunta entre SIGTERM (graceful) e SIGKILL (forçado), explicando a diferença em cada execução.
- **Cache mtime+size** — invalidação automática; sessões ativas sempre bypassam.

## Pendências fora da Wave 3 (Wave 4 ou backlog)

- `pipx install` global da v0.3.0 + v0.4.0
- `gh repo create mencoding/kiro-dashboard --private` + push
- Registrar MCP `kiro-dash` em `~/.kiro/agents/nyx.json`
- Auto-detect de plano via Bearer token AWS (frágil; só fazer se virar dor real)
- Kill por PGID em `audit kill` (matar subagents/MCPs juntos)
- Polling opt-in em outras abas da TUI
- Investigar `~/.local/share/kiro-cli/data.sqlite3` como fonte adicional
