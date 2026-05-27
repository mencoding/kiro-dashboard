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

## Mapeamento de projetos (heurística)

O `kiro-dash` consolida sessões em "projetos conceituais" mapeando o
`cwd` da sessão em um label. Regras (na ordem):

| Padrão de path | Label |
|---|---|
| `~/iris/projetos/<categoria>/<projeto>/...` (categorias: pessoal, profissional, institucional, concluidos) | `<categoria>/<projeto>` |
| `~/iris/projetos/normativos/...` | `iris-normativos` |
| `~/iris/projetos/referencias/...` | `iris-referencias` |
| `~/iris/projetos/...` (sem categoria) | `iris-projetos` |
| `~/iris/...` | `iris-geral` |
| `~/Desenvolvimento/ifsp/<grupo>/<repo>/...` | `ifsp/<grupo>/<repo>` |
| `~/Desenvolvimento/<conta>/<repo>/...` | `<conta>/<repo>` |
| `~/nyx/...` | `nyx` |
| Outros sob `~` | path relativo ao home |
| Fora do home | path literal |

Override declarativo (`config.toml` com aliases custom) está disponível —
ver seção abaixo.

## Aliases de projeto (override declarativo)

Aliases têm prioridade sobre a heurística. Match por prefixo: o mais
específico vence.

```bash
kiro-dash aliases set /srv/work/clientes/acme acme
kiro-dash aliases set /home/foo/lab experimentos
kiro-dash aliases get
kiro-dash aliases unset /srv/work/clientes/acme
```

Persistido em `~/.config/kiro-dash/config.toml` na seção
`[project_aliases]`.

## Filtro por agent

```bash
kiro-dash today --agent nyx
kiro-dash projects --agent kiro_default --window cycle
kiro-dash models --agent nyx --window month
kiro-dash recent --agent nyx
```

`--agent <name>` isola a atividade de um agent específico (comparação
por igualdade exata em `session.agent_name`).

## Filtros temporais

Comandos `today`, `projects` e `models` aceitam `--window`:

```bash
kiro-dash projects --window today        # só hoje
kiro-dash projects --window week         # últimos 7 dias (default)
kiro-dash projects --window month        # últimos 30 dias
kiro-dash projects --window cycle        # desde cycle_start do plano
kiro-dash projects --window all          # tudo desde sempre
kiro-dash projects --window 14           # últimos 14 dias
```

`--days N` segue funcionando como atalho legacy (override de `--window`).

## Cache do parser

Leituras de `.json`/`.jsonl` são memoizadas em
`~/.cache/kiro-dash/` (ou `$XDG_CACHE_HOME/kiro-dash/`). Invalidação
automática por `mtime + size`. Sessões em curso (com `.lock`) bypassam
o cache para garantir frescor.

```bash
kiro-dash cache info     # estatísticas
kiro-dash cache clear    # limpa tudo
```

Para desligar pontualmente: `KIRO_DASH_NO_CACHE=1 kiro-dash today`.

### Benchmark (21 sessões, 2026-05-26)

| Cenário | real |
|---|---|
| Sem cache | 0.089s |
| Com cache (1ª — popular) | 0.090s |
| Com cache (2ª — hit) | 0.090s |

> Com 21 sessões o startup do Python domina. O ganho será visível com
> workspaces maiores (50+ sessões) onde o parse JSON é o gargalo.
## Watchdog operacional (audit)

Sem hooks, sem root. Lê os arquivos `.json`/`.lock` que o Kiro CLI já
gera nativamente.

### Inspecionar

```bash
kiro-dash audit running                  # sessões com turn em curso
kiro-dash audit stuck --threshold 600    # turns em curso > 10 min
kiro-dash audit log <sid> --tail 20      # tool calls da sessão
kiro-dash audit watch                    # live (refresh 2s, Ctrl+C sai)
```

### Matar processo travado

```bash
kiro-dash audit kill <sid>               # interativo: TERM / KILL / cancel
kiro-dash audit kill --all-stuck         # mata todas travadas
kiro-dash audit kill --all-stuck --yes   # sem confirmação
```

**SIGTERM** (graceful): pede ao Kiro que feche. Pode demorar segundos
mas preserva o estado da sessão (`.json` é finalizado, `.jsonl` flusha).

**SIGKILL** (forçado): kernel mata na hora. Estado pode ficar
inconsistente. Use quando SIGTERM não responder.

### Limitações

- Detecta travamento com base em "turn em curso há > threshold". Não há
  heurística para distinguir "travado" de "trabalhando muito". Calibre
  o threshold conforme uso (3m para tarefas curtas, 30m para builds).
- Mata o processo do shell que executa `kiro-cli`, não dependências
  spawn-adas (subagents, MCPs). Para garantir, `kill -SIGKILL -PGID`
  pode ser melhor — não implementado por enquanto.

## Drill-down de tools

```bash
kiro-dash tool shell                       # últimas 20 chamadas de shell
kiro-dash tool write --errors-only         # só erros
kiro-dash tool read --tail 5 --hours 6     # últimas 5 em 6h
```

Mostra: status, toolUseId, input keys (sem values), error summary
(1ª linha do retorno quando status=error, capped 200 chars).

Privacidade: `input.values` não são retidos pelo parser (Wave 1).
`error_summary` é metadata operacional (FileNotFoundError, exit code,
HTTP status), não vaza prompts.

Na TUI, aba Tools (`5`): seleção de linha (↑/↓ + Enter) abre painel
inferior com top 5 erros recentes.

## Notas técnicas

### Clock injetável

Funções de janela temporal do `aggregator` aceitam um kwarg
opcional `now: datetime | None = None`. Quando ausente, usa
`datetime.now(timezone.utc)`. Quando passado, é fonte única do "agora".

Habilita:
- Testes determinísticos timezone-safe (sem `freezegun`)
- Replay/snapshot histórico que precisa "fingir" um momento passado
- Auditoria que reproduz cálculos de uma data específica

## Licença

Privado — uso pessoal de Leonardo Menzani.
