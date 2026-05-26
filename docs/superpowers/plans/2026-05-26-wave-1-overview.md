# Wave 1 — Overview

**Data:** 2026-05-26
**Versão alvo:** v0.2.0
**Princípio:** três frentes independentes, cada uma em branch própria, mergeáveis em qualquer ordem.

## Frentes

| Frente | Plano | Branch | Esforço estimado |
|---|---|---|---|
| **A** — `projects` + `models` + `recent` | [`2026-05-26-projects-models-recent.md`](2026-05-26-projects-models-recent.md) | `feat/wave1-projects-models-recent` | 1-2h |
| **B** — `tools` (parsing `.jsonl`) | [`2026-05-26-tools-subcommand.md`](2026-05-26-tools-subcommand.md) | `feat/wave1-tools` | 2-3h |
| **C** — MCP server | [`2026-05-26-mcp-server.md`](2026-05-26-mcp-server.md) | `feat/wave1-mcp-server` | 2-3h |

## Conflitos esperados

- **`pyproject.toml`**: Frente C adiciona dep `mcp` e entry `kiro-dash-mcp`. Frentes A e B não tocam o arquivo. Sem conflito real.
- **`src/kiro_dash/cli.py`**: as 3 frentes adicionam comandos novos (Frente A: 3, Frente B: 1, Frente C: 0). Conflito de adição local — resolução trivial via "aceitar ambos" no merge.
- **`src/kiro_dash/aggregator.py`**: A adiciona `turns_in_last_days`; B adiciona `aggregate_tools_in_window`. Funções diferentes, sem conflito real.
- **`tests/test_aggregator.py`**: A e B podem criar/modificar este mesmo arquivo. **Convenção:** quem chegar primeiro cria o arquivo, o segundo só acrescenta.
- **`tests/fixtures/sessions_synthetic.py`**: criado pela Frente A. Frente C importa dela (depende). **Ordem sugerida:** A primeiro (ou em paralelo, com aviso ao subagent C de que pode precisar criar o helper se A ainda não rodou).

## Dependências cruzadas (importante)

- **Frente C → Frente A**:
  - `tool_top_projects` e `tool_top_models` em `mcp_server.py` importam `turns_in_last_days` (criado pela Frente A Task 2).
  - Os testes da Frente C importam `tests/fixtures/sessions_synthetic.py` (criado pela Frente A Task 1).
- **Frente B independente** das outras duas (só toca em arquivos novos + adições aditivas).

**Ordem prática sugerida:**

1. **Frente A Task 1** (fixtures sintéticas) — habilitador comum, 5 min de trabalho.
2. **Frente A Task 2** (`turns_in_last_days`) — habilita Frente C.
3. A partir daí, **Frentes A (Task 3+), B e C podem rodar em paralelo**.
4. Merge ordenado: A → C (se serial), ou conjunto (se paralelo via worktrees).

## Critério de "wave concluída"

- Todos os planos com checkboxes marcados (`- [x]`)
- `pytest -v` no branch consolidado → todos passam (incluindo testes existentes)
- Smoke manual de cada subcomando contra dados reais
- Tag `v0.2.0` aplicada ao merge

## Decisões já tomadas

- **Statusline removida** da Wave 1: Kiro CLI não tem feature equivalente ao `statusLine.command` do Claude Code (verificado).
- **Filtros temporais (`--week`, `--month`, range custom)**: ficam para Wave 2 — conflito leve com Frente A se feitos juntos, e a flag `--days N` já cobre 80% do uso.
- **Cache em `~/.cache/kiro-dash/`**: Wave 2. Parsing está rápido o suficiente.
- **TUI Textual**: Wave 2 separada — esforço grande, mexe em `cli.py` significativamente.
- **Audit hook do Kiro**: projeto/escopo separado, não Wave 1.
