# Wave 5 — Overview

**Data:** 2026-05-27
**Versão alvo:** v0.6.0
**Princípio:** persistência histórica em 4 frentes encadeadas em 3 ondas.

## Frentes

| Frente | Plano | Branch | Esforço | Depende de |
|---|---|---|---|---|
| **L** — Clock injetável | [`2026-05-27-wave5-clock.md`](2026-05-27-wave5-clock.md) | `feat/wave5-clock` | 3-4h | — |
| **M** — Snapshot diário + lazy + self-healing | [`2026-05-27-wave5-snapshot.md`](2026-05-27-wave5-snapshot.md) | `feat/wave5-snapshot` | 5-7h | L |
| **N** — Queries históricas | [`2026-05-27-wave5-history-queries.md`](2026-05-27-wave5-history-queries.md) | `feat/wave5-history-queries` | 4-5h | L + M |
| **O** — TUI History tab + comparativos | [`2026-05-27-wave5-tui-history.md`](2026-05-27-wave5-tui-history.md) | `feat/wave5-tui-history` | 4-5h | L + M + N |

Total: 16-21h em 3 ondas.

## Dependências

```
L (Clock) ──┐
            ↓
M (Snapshot) ──┐
               ↓
N (Queries) + O (TUI) ──→ Wave 5 done (v0.6.0)
```

## Ordem de execução

### Onda 1 — sequencial

L sozinho (3-4h). Refactor do aggregator, base de tudo.

### Onda 2 — sequencial

M sozinho (5-7h). Cria `snapshots.py`, `kiro-dash snapshot`, integração lazy.

### Onda 3 — paralela

N + O em worktrees separados (5h cada). N entrega CLI (`month`/`year`/`compare`); O entrega TUI History tab.

## Conflitos esperados

Triviais e aditivos:
- `cli.py` — N adiciona `month`/`year`/`compare`; O não toca CLI
- `views/styles.tcss` — O adiciona regras `HistoryTab`
- `views/app.py` — O adiciona TabPane History e bind `7`
- `README.md` — N e O adicionam seções

## Decisões consolidadas (com Léo)

1. **Granularidade:** só **diário**; mensal/anual reconstruídos on-the-fly.
2. **Geração:** **lazy** (na primeira execução depois do fim do dia X) **+ self-healing** (cada execução verifica buracos nos últimos 30 dias) **+ manual** (`kiro-dash snapshot YYYY-MM-DD`).
3. **Storage:** JSON files em `~/.local/share/kiro-dash/snapshots/<YYYY-MM-DD>.<host>.json`.
4. **Janela stateless:** hoje + ontem **nunca** persistem — sempre re-lidos dos `.json` originais. Snapshot só fecha em D-2.
5. **Multi-host:** snapshots de hosts diferentes coexistem (`<date>.<host>.json`); query soma todos.
6. **Comparativos visuais:** hoje × ontem, semana × semana passada, mês × mês passado, ano × ano passado — 4 cards em grid 2×2 na TUI.

## Pendências fora da Wave 5 (Wave 6+)

- Pendências operacionais ainda abertas:
  - `pipx install --force ~/Desenvolvimento/mencoding/kiro-dash`
  - `gh repo create mencoding/kiro-dashboard --private` + push
  - MCP `kiro-dash` em `~/.kiro/agents/nyx.json`
- Polling opt-in em outras abas da TUI
- Compactação de snapshots > 1 ano (gz?)
- Auto-migração de schema_version
- Investigar `~/.local/share/kiro-cli/data.sqlite3` como fonte adicional
