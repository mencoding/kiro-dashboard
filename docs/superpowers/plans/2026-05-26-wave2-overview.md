# Wave 2 — Overview

**Data:** 2026-05-26
**Versão alvo:** v0.3.0
**Princípio:** 4 frentes, encadeadas em 2 ondas paralelas para minimizar conflitos.

## Frentes

| Frente | Plano | Branch | Esforço | Frentes que destrava |
|---|---|---|---|---|
| **D** — Sync multi-device (rclone) | [`2026-05-26-wave2-sync.md`](2026-05-26-wave2-sync.md) | `feat/wave2-sync` | 2h | — |
| **E** — Plan + saldo estimado | [`2026-05-26-wave2-plan-balance.md`](2026-05-26-wave2-plan-balance.md) | `feat/wave2-plan-balance` | 3h | G (resolve_window cycle) |
| **F** — TUI Textual (6 abas) | [`2026-05-26-wave2-tui.md`](2026-05-26-wave2-tui.md) | `feat/wave2-tui` | 8-10h | G (Task 4 ajusta tabs) |
| **G** — Filtros temporais + heurística de projeto | [`2026-05-26-wave2-projects-windows.md`](2026-05-26-wave2-projects-windows.md) | `feat/wave2-projects-windows` | 4-5h | (consome E e F) |

Total estimado: 17-20h, cabe em 2-3 sessões reais.

## Dependências

```
D (sync)        ─────────────────┐
                                 │
E (plan/balance) ──┐             │
                   │             │
                   ↓             │
F (tui) ───────────┘             │
                   │             │
                   ↓             │
G (projects/windows) ────────────┘
                                 │
                                 ↓
                              Wave 2 done
```

- **D é totalmente independente** — pode rodar em qualquer momento.
- **E destrava G** (Task 2 do G usa `cycle_start` do plano para `resolve_window("cycle", ...)`).
- **F destrava G Task 4** (Task 4 do G modifica `projects_tab.py` e `models_tab.py` que F cria).
- **G consome E e F** — é a última a rodar.

## Ordem prática sugerida

### Onda 1 — paralelo total (3 worktrees)

| Worktree | Frente |
|---|---|
| `.worktrees/wave2-sync` | **D** |
| `.worktrees/wave2-plan-balance` | **E** |
| `.worktrees/wave2-tui` | **F** (sem heurística ainda — usa `aggregate_by_cwd` existente) |

Após terminarem: merge D → E → F no main.

### Onda 2 — sequencial

| Worktree | Frente |
|---|---|
| `.worktrees/wave2-projects-windows` | **G** (a partir do main pós-F) |

Merge G no main. Tag `v0.3.0`.

## Conflitos esperados

- **`pyproject.toml`** — D adiciona `kiro-dash-sync` em `[project.scripts]`; E adiciona dep `tomli_w`; F adiciona dep `textual` + dep `pytest-asyncio`. Conflitos de adição triviais (resolução: aceitar todos).
- **`src/kiro_dash/cli.py`** — D adiciona grupo `sync`; E adiciona grupo `plan` e comando `balance`; F adiciona comando `tui`; G adiciona/modifica flags `--window` em `today/projects/models`. Conflitos de adição triviais; só G **modifica** comandos existentes (substitui body de `projects` e `models`), o que é aplicado contra a versão pós-F.
- **`README.md`** — todas as 4 frentes adicionam seções. Conflito de adição trivial.
- **`tests/test_aggregator.py`** — E adiciona testes de balance; G adiciona teste de aggregate_by_project. Não conflitam (sections distintas), mas merge em série recomendado.

## Critério de wave concluída

- Todos os planos com checkboxes marcados (`- [x]`)
- `pytest -v` no main → todos os testes passam (Wave 1 + Wave 2)
- Smoke manual:
  - `kiro-dash sync push/pull` (com rclone configurado)
  - `kiro-dash plan set pro+` + `kiro-dash balance`
  - `kiro-dash tui` interativo: 6 abas, `r` refresh, `q` sai
  - `kiro-dash projects --window cycle` consolidado por heurística
- Tag `v0.3.0` aplicada ao merge

## Decisões consolidadas (registradas com Léo)

- **TUI auto-refresh seletivo** — Now atualiza sozinha a cada 2s (`NOW_REFRESH_SEC = 2.0`); Today/Projects/Models/Tools/Session ficam manuais via `r`. Mesmo padrão do `claude-dash` em produção, justificado pelo custo de re-render das abas que reparseiam transcripts inteiros.
- **Sync exclui `.jsonl`** — só metadata de sessão (`.json`) entra no Drive.
- **Heurística project_label hardcoded** — categorias `pessoal/profissional/institucional/concluidos` reconhecidas; subpasta `geral` dentro de cada vira `<categoria>/geral` naturalmente. Override TOML é Wave 3.
- **Auto-detect de plano via API** — fora desta wave (API privada AWS Q Developer, frágil). TOML declarativo é a fonte de verdade.

## Pendências fora da Wave 2 (registradas para Wave 3)

- Auto-detect de plano via Bearer token em `~/.aws/sso/cache/kiro-auth-token-cli.json`
- Override declarativo de `project_label` via `[project_aliases]` no TOML
- Cache em `~/.cache/kiro-dash/` (parser cresce, viagem barata se virar lento)
- Audit hook (espelho do `claude-dash-audit-hook` para o Kiro CLI) — investigação separada dos matchers do Kiro
- Push pro GitHub (`gh repo create mencoding/kiro-dashboard --private` + push)
