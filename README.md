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

## Sync multi-device (Google Drive via rclone)

Sincroniza apenas os `.json` de `~/.kiro/sessions/cli/` entre dispositivos —
o painel de uma máquina passa a ver sessões da outra. **Não inclui** os
`.jsonl` (transcripts com prompts/respostas; ficam locais).

### Pré-requisitos

- `rclone` instalado e remote `gdrive-pessoal` configurado (mesmo padrão do
  `iris/sync-drive.sh`):
  ```bash
  sudo apt install rclone
  rclone config   # criar remote tipo 'drive', nome 'gdrive-pessoal'
  ```

### Uso manual

```bash
kiro-dash sync push   # local → Drive
kiro-dash sync pull   # Drive → local
```

### Uso automatizado (hook do agent Nyx)

No `~/.kiro/agents/nyx.json`, em `hooks.agentSpawn`:

```json
"agentSpawn": [
  { "command": "kiro-dash sync pull --remote gdrive-pessoal", "timeout_ms": 30000 }
]
```

E em `hooks.stop`:

```json
"stop": [
  { "command": "kiro-dash sync push --remote gdrive-pessoal", "timeout_ms": 30000 }
]
```

### Privacidade

- Apenas `.json` é syncado (metadata + título de sessão; sem conteúdo de mensagens)
- `.jsonl` (transcripts) **NÃO** sai do dispositivo
- `.lock` (estado local) **NÃO** sai do dispositivo

## Licença

Privado — uso pessoal de Leonardo Menzani.
