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

## Plano e saldo estimado

Declare seu plano para que o painel mostre saldo restante do ciclo:

```bash
kiro-dash plan set pro+              # 2000 créditos/mês (default da tier)
kiro-dash plan set pro --credits 1500 --cycle-start 2026-05-15  # overrides
kiro-dash plan get
kiro-dash balance                    # painel dedicado
kiro-dash today                      # mostra linha de contexto do ciclo
```

Tiers reconhecidas: `free` (50), `pro` (1000), `pro+` (2000), `power`
(10000), `enterprise` (sem cap real).

Alertas visuais: amarelo a partir de 80%, vermelho a partir de 95%.

Config persiste em `~/.config/kiro-dash/config.toml`.

> **Nota:** o saldo é estimativa local — se você usa Kiro em mais de um
> dispositivo sem o `kiro-dash sync` ativo, o consumo real pode ser maior
> que o calculado aqui. Dashboard web (`kiro-cli dashboard`) é a fonte
> autoritativa.

## Licença

Privado — uso pessoal de Leonardo Menzani.
