# kiro-dashboard

Painel local de uso e créditos do **Kiro CLI** (ex-Amazon Q Developer CLI).
Lê as sessões gravadas em `~/.kiro/sessions/cli/` e expõe consumo
agregado, drill-down por sessão, e visão "tempo real" das sessões
ativas.

## Motivação

O Kiro CLI cobra por **créditos** (não tokens) e não expõe via CLI
nativa uma visão transversal de quanto cada sessão consumiu, qual
modelo usou, em qual projeto, com qual agent. Esses dados existem em
`~/.kiro/sessions/cli/<sid>.json`, no campo
`session_state.conversation_metadata.user_turn_metadatas[].metering_usage[]`
— este projeto consolida tudo num único painel local.

Inspirado no [`claude-dashboard`](https://github.com/mencoding/claude-dashboard).

## Princípio de privacidade

O parser é **deliberadamente cego para o conteúdo de mensagens**. Lê
apenas metadata estrutural: créditos, modelo, agent, projeto (cwd),
timestamps, ferramentas (count), % de contexto. Prompts e respostas
do usuário/assistente nunca entram no índice.

## Uso (planejado)

```bash
kiro-dash whoami         # conta, organização, profile, billing tier
kiro-dash now            # live view das sessões ativas
kiro-dash today          # agregado do dia
kiro-dash session <sid>  # drill-down (prefixo de sessionId aceito)
kiro-dash projects       # top projetos por créditos
kiro-dash models         # top modelos
```

## Instalação (planejado)

```bash
pipx install ~/Desenvolvimento/mencoding/kiro-dash
```

## Status

**v0.1.0** — em construção. Roadmap em `ROADMAP.md` (a criar).

## Stack

- Python 3.12
- [`rich`](https://rich.readthedocs.io) — output e Live view
- [`click`](https://click.palletsprojects.com) — CLI
- Parsing nativo de JSON (sem dependência externa)

## MCP server — canal para outros agentes

A partir da v0.2 o `kiro-dash-mcp` expõe o estado do Kiro CLI como
ferramentas consultáveis via Model Context Protocol. Útil para agentes
fazerem meta-raciocínio sobre o próprio uso de créditos.

Registrar no Kiro CLI (assumindo que `kiro-dash-mcp` está no `PATH`):

```json
// Em mcpServers do agent config:
"kiro-dash": {
  "command": "kiro-dash-mcp"
}
```

Tools expostas:

| Tool | Retorna |
|---|---|
| `today_summary` | Agregado do dia local |
| `active_sessions` | Sessões com lockfile no momento |
| `session_details(session_id_prefix)` | Drill-down (estrutural; sem conteúdo) |
| `account_info` | Conta, profile ARN, billing tier |
| `top_projects(days, limit)` | Top projetos por créditos |
| `top_models(days, limit)` | Top modelos por créditos |

**Privacidade:** nenhuma tool expõe conteúdo de mensagens — apenas
metadata estrutural (mesma superfície da CLI).

## TUI interativa

```bash
kiro-dash tui
```

Atalhos:

| Tecla | Ação |
|---|---|
| `1` | Aba Now (sessões ativas) |
| `2` | Aba Today |
| `3` | Aba Projects |
| `4` | Aba Models |
| `5` | Aba Tools |
| `6` | Aba Session (com seleção e drill-down) |
| `←` / `→` | Navegar abas (bind padrão do Textual) |
| `r` | Refresh manual da aba ativa |
| `?` | Ajuda |
| `q` | Sair |

**Auto-refresh seletivo** (mesmo padrão do `claude-dash` em produção):
- **Now** atualiza sozinha a cada 2s (`NOW_REFRESH_SEC = 2.0`).
- Demais abas são snapshot — pressione `r` para recomputar quando quiser.
- Razão: Today/Tools/Session re-leem todas as sessões ou os transcripts
  `.jsonl` inteiros; refresh contínuo seria caro.

## Licença

Privado — uso pessoal de Leonardo Menzani.
