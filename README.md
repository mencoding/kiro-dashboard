# kiro-dashboard

[![Version](https://img.shields.io/badge/version-0.7.0-blue)](https://github.com/mencoding/kiro-dashboard/releases)
[![Python](https://img.shields.io/badge/python-3.12+-blue)](https://www.python.org)
[![License](https://img.shields.io/badge/license-Proprietary-red)](#licença)

Painel local de uso e créditos do **Kiro CLI** (ex-Amazon Q Developer CLI).
Lê as sessões gravadas em `~/.kiro/sessions/cli/` e expõe consumo
agregado, drill-down por sessão/tool, watchdog de processos travados,
histórico persistido e visão "tempo real" em TUI ou MCP.

Inspirado no [`claude-dashboard`](https://github.com/mencoding/claude-dashboard).

---

## Sumário

- [Motivação](#motivação)
- [Privacidade](#privacidade)
- [Instalação](#instalação)
- [Início rápido](#início-rápido)
- [Comandos](#comandos)
  - [Identidade e conta](#identidade-e-conta)
  - [Visão imediata](#visão-imediata)
  - [Janelas e drill-downs](#janelas-e-drill-downs)
  - [Plano e saldo](#plano-e-saldo)
  - [Histórico](#histórico)
  - [Watchdog operacional](#watchdog-operacional-audit)
  - [Sync multi-device](#sync-multi-device)
  - [Cache, aliases, configuração](#cache-aliases-configuração)
- [TUI interativa](#tui-interativa)
- [Heurística de projetos](#heurística-de-projetos)
- [Servidor MCP](#servidor-mcp)
- [Suporte multi-source](#suporte-multi-source-wave-6--v070)
- [Stack e arquitetura](#stack-e-arquitetura)
- [Licença](#licença)

---

## Motivação

O Kiro CLI cobra por **créditos** (não tokens) e não expõe via CLI nativa
uma visão transversal de quanto cada sessão consumiu, qual modelo usou,
em qual projeto, com qual agent. Esses dados existem em
`~/.kiro/sessions/cli/<sid>.json`, no campo
`session_state.conversation_metadata.user_turn_metadatas[].metering_usage[]`.
Este projeto consolida tudo num único painel local — CLI, TUI ou MCP.

## Privacidade

O parser é **deliberadamente cego para o conteúdo de mensagens**. Lê
apenas metadata estrutural:

- créditos, modelo, agent, projeto (cwd), timestamps
- nomes de tool calls, status (success/error), `error_summary` (1ª linha
  do retorno em caso de erro — sem prompts)
- `input_keys` das tools (apenas nomes dos parâmetros, sem values)

Prompts e respostas do usuário/assistente **nunca** entram no índice,
cache, snapshots ou MCP. O sync via rclone (opcional) inclui apenas
`.json` (metadata); `.jsonl` (transcripts) **nunca** sai do dispositivo.

---

## Instalação

```bash
pipx install git+https://github.com/mencoding/kiro-dashboard.git
```

Ou versão fixa:

```bash
pipx install git+https://github.com/mencoding/kiro-dashboard.git@v0.6.1
```

3 binários globais ficam disponíveis:

- `kiro-dash` — CLI principal e TUI
- `kiro-dash-mcp` — servidor MCP (stdio)
- `kiro-dash-sync` — alias do `kiro-dash sync`

**Pré-requisitos:**

- Python 3.12+
- Kiro CLI já em uso (com sessões em `~/.kiro/sessions/cli/`)
- Para sync opcional: `rclone` configurado

## Início rápido

```bash
# Identidade
kiro-dash whoami

# Hoje
kiro-dash today

# TUI completa
kiro-dash tui

# Plano + saldo do ciclo
kiro-dash plan set pro+
kiro-dash balance

# Histórico
kiro-dash month             # mês corrente
kiro-dash compare today yesterday
```

---

## Comandos

### Identidade e conta

```bash
kiro-dash whoami            # conta AWS, profile, billing tier
```

### Visão imediata

```bash
kiro-dash now               # sessões ativas (com lockfile presente)
kiro-dash today             # agregado do dia local
kiro-dash today --day 2026-05-16   # dia específico (lê snapshot se < D-2)
kiro-dash recent            # últimas N sessões
kiro-dash session <sid>     # drill-down (prefixo aceito)
```

### Janelas e drill-downs

```bash
kiro-dash projects                  # top projetos (default: últimos 7d)
kiro-dash models                    # top modelos
kiro-dash tools                     # tool calls últimas 24h (com bar visual)

# Filtros temporais (--window):
kiro-dash projects --window today
kiro-dash projects --window week    # default
kiro-dash projects --window month
kiro-dash projects --window cycle   # desde cycle_start do plano
kiro-dash projects --window all
kiro-dash projects --window 14      # int = N dias

# Filtro por agent:
kiro-dash today --agent nyx
kiro-dash projects --agent kiro_default --window cycle

# Drill-down de tool específica:
kiro-dash tool shell                # últimas 20 chamadas
kiro-dash tool write --errors-only  # só erros
kiro-dash tool read --tail 5 --hours 6
```

`--days N` e `--window <n>` são equivalentes (legacy + novo). `--show-input`
no `tool` mostra também as keys do input (values nunca são retidos).

### Plano e saldo

```bash
kiro-dash plan get
kiro-dash plan set pro+              # 2000 cr/mês (default da tier)
kiro-dash plan set pro --credits 1500 --cycle-start 2026-05-15
kiro-dash balance                    # saldo do ciclo corrente
kiro-dash balance --no-ide           # força estimativa local (ignora IDE)
```

Tiers reconhecidas: `free` (50), `pro` (1000), `pro+` (2000), `power`
(10000), `enterprise` (sem cap real). Alertas visuais: amarelo a partir
de 80%, vermelho a partir de 95%. Config persiste em
`~/.config/kiro-dash/config.toml`.

#### Saldo autoritativo via Kiro IDE (v0.7.0+)

Quando o **Kiro IDE** está instalado e foi aberto recentemente,
`balance` lê o billing autoritativo do servidor diretamente do
`state.vscdb` do IDE — sem estimativa, sem heurística. O IDE faz
fetch periódico do servidor enquanto está aberto, refletindo consumo
**global da conta** (CLI + IDE + Web) e não apenas o que rodou
localmente.

Quando o IDE **não está instalado ou nunca foi aberto**, `balance`
cai para estimativa local baseada no plano declarado via `plan set`,
exibindo a mesma saída pré-v0.7.0. Um banner sugere a instalação
(suprimível com `KIRO_DASH_NO_BANNER=1`).

`plan get` também exibe os limites observados pelo servidor quando o
IDE está disponível: `usageLimit`, `overageCap`, `overageRate` e data
de reset. Os valores manuais de `plan set` continuam sendo
respeitados — a leitura do IDE é **informativa**, não sobrescreve
config local.

**Política de frescor.** O snapshot do `state.vscdb` carrega um
timestamp; quando ele envelhece, a UI mostra um badge:

| Idade | Cor | Mensagem |
|---|---|---|
| < 3 h | verde | (nenhuma) |
| 3 h – 12 h | amarelo | `snapshot de Xh atrás` |
| 12 h – 24 h | vermelho | `snapshot de Xh atrás — abra o Kiro IDE para refresh` |
| ≥ 24 h | cinza | `snapshot stale (Xd) — saldo pode estar muito desatualizado` |

Para refrescar, basta abrir o Kiro IDE — o cache é atualizado em
background a cada ~30-60 segundos enquanto rodando. Detalhes de
arquitetura: [`docs/adr/0001-multi-backend-architecture.md`](docs/adr/0001-multi-backend-architecture.md).

### Histórico

Snapshots imutáveis de uso por dia em
`~/.local/share/kiro-dash/snapshots/<YYYY-MM-DD>.<host>.json`.

```bash
# Geração (lazy + self-healing automático nos comandos consumidores):
kiro-dash snapshot                   # gera snapshots faltantes (até ontem)
kiro-dash snapshot 2026-05-16        # gera/garante dia específico
kiro-dash snapshot 2026-05-16 --force # sobrescreve

# Consultas:
kiro-dash today --day 2026-05-16     # snapshot ou live (D, D-1 são live)
kiro-dash month                      # mês corrente
kiro-dash month 2026-05
kiro-dash year                       # ano corrente
kiro-dash year 2026

kiro-dash compare today yesterday
kiro-dash compare week last-week
kiro-dash compare month last-month
kiro-dash compare 2026-05 2026-04
kiro-dash compare 2026 2025
```

**Janela stateless de 2 dias:** hoje e ontem são sempre re-lidos dos
`.json` originais. Snapshot só fecha em **D-2 ou anterior**.

**Multi-host:** snapshots de hosts distintos coexistem
(`2026-05-16.predator.json` + `2026-05-16.work.json`). Queries somam
todos os hosts.

### Watchdog operacional (audit)

Sem hooks, sem root. Lê `.json` + `.lock` nativos do Kiro.

```bash
# Inspecionar:
kiro-dash audit running              # sessões com turn em curso AGORA
kiro-dash audit stuck --threshold 600 # turns em curso > 10 min
kiro-dash audit log <sid> --tail 20  # tool calls da sessão
kiro-dash audit watch                # live (refresh 2s, Ctrl+C sai)

# Matar processo travado:
kiro-dash audit kill <sid>           # interativo: TERM / KILL / cancel
kiro-dash audit kill --all-stuck
kiro-dash audit kill --all-stuck --yes
```

**SIGTERM** (graceful): pede ao Kiro pra fechar; preserva estado.
**SIGKILL** (forçado): kernel mata na hora; estado pode ficar
inconsistente. Use quando SIGTERM não responder.

> Detecta travamento por "turn em curso há > threshold". Não distingue
> "travado" de "trabalhando muito". Calibre o threshold (3m para tarefas
> curtas, 30m para builds longos).

### Sessões do Kiro IDE (Wave 6, frente Q)

Quando o **Kiro IDE** está instalado, o `kiro-dash` também enxerga
sessões executadas dentro do IDE — não apenas via CLI. Cada
``execution`` registrada pelo IDE em
``~/.config/Kiro/User/globalStorage/kiro.kiroagent/`` vira um
``Turn`` no domínio interno, com créditos por fase, intent
classification (``chat``/``do``/``spec``) e tools usadas.

A seleção de fonte se dá via flag `--source`:

```bash
kiro-dash recent --source ide        # só sessões IDE
kiro-dash recent --source all        # CLI + IDE concatenados (coluna source)
kiro-dash recent --source cli        # default — só CLI (retro-compat)

kiro-dash audit running --source all # sessões em curso de ambas fontes
kiro-dash session <prefix>           # auto-resolve em ambas fontes; --source força
```

Comandos suportando `--source` na frente Q: `recent`, `audit running`,
`session <prefix>`. Os agregados (`today`, `projects`, `models`,
`tools`) continuam só-CLI até a frente R, que entrega o aggregator
multi-source.

**Identidade composta:** sessões IDE têm `session_id` prefixado
(`ide-sessions:<uuid>`) para diferenciá-las de sessões CLI. Comandos
e tools MCP aceitam tanto o prefixo composto quanto o UUID raw.

**Heurística "live" do IDE** (decisão #10 do plano frente Q):
catálogo de executions (`f62de366d0006e17ea00a01f6624aabf`) traz
status; se alguma execution tem `status="running"` e `endTime=0`, a
sessão é considerada live. Isso é equivalente ao `.lock` do CLI, mas
sem precisar de filesystem locking.

**Workflows observados** (decisão #4 do plano):

| `workflowType` | `intent.classification` | Cenário |
|---|---|---|
| `chat-agent` | `chat` | Pergunta simples |
| `chat-agent` | `do` | Autopilot executa (read/write/bash/control) |
| `chat-agent` | `spec` | Dispatcha para specAgent (pequeno) |
| `spec-generation` | (ausente) | Sub-execução pesada que gera arquivos da spec |

Pedido de spec dispara **2 executions encadeadas** com mesmo
`chatSessionId`. Por default, cada execution = 1 turn. A consolidação
"spec lógico" (somar créditos das duas) fica para a frente R com o
aggregator multi-source.

**Privacidade preservada:** o reader IDE é tão cego quanto o CLI —
nunca lê `actions[].input.content`, `actions[].say.message`,
`history[].message` nem `editorState`. Apenas metadata estrutural
(IDs, timestamps, `usageSummary`, `intentResult.classification`).

### Sync multi-device

Sincroniza apenas `.json` (metadata) entre dispositivos via Google Drive.
**Não inclui** `.jsonl` (transcripts ficam locais).

```bash
kiro-dash sync push                  # local → Drive
kiro-dash sync pull                  # Drive → local
```

**Pré-requisitos:** `rclone` instalado e remote `gdrive-pessoal`
configurado (`rclone config`).

**Hooks no agent Nyx** (em `~/.kiro/agents/nyx.json`):

```json
"hooks": {
  "agentSpawn": [{ "command": "kiro-dash sync pull --remote gdrive-pessoal", "timeout_ms": 30000 }],
  "stop":       [{ "command": "kiro-dash sync push --remote gdrive-pessoal", "timeout_ms": 30000 }]
}
```

### Cache, aliases, configuração

**Cache do parser** (`~/.cache/kiro-dash/`, mtime+size invalidation):

```bash
kiro-dash cache info                 # estatísticas
kiro-dash cache clear                # limpa
KIRO_DASH_NO_CACHE=1 kiro-dash today # bypass pontual
```

Sessões com `.lock` ativo bypassam cache automaticamente.

**Aliases de projeto** (override declarativo da heurística):

```bash
kiro-dash aliases set /srv/work/clientes/acme acme
kiro-dash aliases set /home/foo/lab experimentos
kiro-dash aliases get
kiro-dash aliases unset /srv/work/clientes/acme
```

Aliases têm prioridade sobre a heurística — match por prefixo, mais
específico vence. Persistido em `~/.config/kiro-dash/config.toml`,
seção `[project_aliases]`.

**Variáveis de ambiente:**

| Var | Default | Propósito |
|---|---|---|
| `KIRO_DASH_NO_CACHE` | unset | bypass do cache do parser para uma execução |
| `KIRO_DASH_IDE_STATE_PATH` | `~/.config/Kiro/User/globalStorage/state.vscdb` | override do path do `state.vscdb` do IDE (frente P) |
| `KIRO_DASH_NO_IDE_STATE` | unset | desabilita leitura do billing IDE (testes/debug) |
| `KIRO_DASH_IDE_SESSIONS_ROOT` | `~/.config/Kiro/User/globalStorage/kiro.kiroagent/` | override do root das sessões IDE (frente Q) |
| `KIRO_DASH_NO_IDE_SESSIONS` | unset | desabilita leitura de sessões IDE (testes/debug) |
| `KIRO_DASH_NO_BANNER` | unset | suprime banner de onboarding sugerindo Kiro IDE |
| `XDG_CONFIG_HOME` | `~/.config` | padrão XDG; muda raiz do `kiro-dash/config.toml` |
| `XDG_CACHE_HOME` | `~/.cache` | padrão XDG; muda raiz do cache e do `banner_state.json` |

---

## TUI interativa

```bash
kiro-dash tui
```

| Tecla | Ação |
|---|---|
| `1` | Now (sessões ativas) |
| `2` | Today (agregado do dia em 4 quadrantes) |
| `3` | Projects (top projetos com heurística) |
| `4` | Models |
| `5` | Tools (com seleção e drill-down inline) |
| `6` | Session (lista todas, ↑/↓ + Enter abre detalhes) |
| `7` | History (sparklines + 4 cards comparativos) |
| `←` / `→` | Navegar abas |
| `r` | Refresh manual |
| `?` | Ajuda |
| `q` | Sair |

**Auto-refresh seletivo:**

- **Now** atualiza sozinha a cada 2s (única aba "live")
- Demais abas: snapshot manual via `r`. Razão: relêem `.json`/`.jsonl`
  inteiros — refresh contínuo seria caro.

**Aba History:** sparklines de 30 dias (créditos/dia) e 12 meses
(créditos/mês) + 4 cards em grid 2×2 mostrando hoje × ontem, semana ×
sem. anterior, mês × mês anterior, ano × ano anterior. Cores por delta
(verde positivo, vermelho negativo).

**Aba Tools:** seleção de linha (↑/↓ + Enter) abre painel inferior com
top 5 erros recentes daquela tool — `error_summary` mostra a 1ª linha do
retorno (FileNotFoundError, exit code, etc.). Sem vazar prompts.

---

## Heurística de projetos

Mapeia `cwd` da sessão em label de projeto (sobrescritível por aliases).
Regras na ordem:

| Padrão de path | Label |
|---|---|
| `~/iris/projetos/<categoria>/<projeto>/...` (categorias: `pessoal`, `profissional`, `institucional`, `concluidos`) | `<categoria>/<projeto>` |
| `~/iris/projetos/normativos/...` | `iris-normativos` |
| `~/iris/projetos/referencias/...` | `iris-referencias` |
| `~/iris/projetos/...` (sem categoria) | `iris-projetos` |
| `~/iris/...` | `iris-geral` |
| `~/Desenvolvimento/ifsp/<grupo>/<repo>/...` | `ifsp/<grupo>/<repo>` |
| `~/Desenvolvimento/<conta>/<repo>/...` | `<conta>/<repo>` |
| `~/nyx/...` | `nyx` |
| `~` (HOME exato) | `home` |
| `~/Downloads`, `~/Documents`, `~/Desktop` (e subpastas) | `home/<nome>` |
| Outros sob `~` | path relativo ao home |
| Fora do home | path literal |

Para custom mappings, use `kiro-dash aliases set`.

---

## Servidor MCP

`kiro-dash-mcp` expõe o estado do Kiro CLI via [Model Context
Protocol](https://modelcontextprotocol.io). Útil para agentes consumarem
métricas durante a conversa, sem precisar abrir terminal.

**Tools expostas:**

| Tool | Retorna | Aceita `source` |
|---|---|---|
| `today_summary` | Agregado do dia local | — (frente R) |
| `active_sessions` | Sessões em curso (lock CLI ou execution.status=running IDE) | ✓ `cli`/`ide`/`all` |
| `session_details(prefix)` | Drill-down (estrutural; sem conteúdo) | ✓ `auto`/`cli`/`ide` |
| `account_info` | Conta, profile ARN, billing tier | — |
| `top_projects(days, limit)` | Top projetos por créditos | — (frente R) |
| `top_models(days, limit)` | Top modelos por créditos | — (frente R) |
| `usage_state` | Billing autoritativo do servidor via Kiro IDE (Wave 6/P) | — |

Tools que aceitam `source` retornam um campo extra `source` em cada
sessão (`"cli"` ou `"ide"`), permitindo ao agente caller distinguir a
fonte sem heurística adicional.

**Registro no Kiro CLI** (em `~/.kiro/agents/<seu-agent>.json`):

```json
"mcpServers": {
  "kiro-dash": {
    "command": "kiro-dash-mcp",
    "timeout_ms": 30000
  }
}
```

Reinicie a sessão Kiro CLI depois.

Mesma superfície de privacidade da CLI — nenhuma tool MCP expõe conteúdo
de mensagens.

---

## Suporte multi-source (Wave 6 / v0.7.0)

A v0.7.0 introduz suporte completo para múltiplas fontes de dados Kiro:
**Kiro CLI** (sessões gravadas em `~/.kiro/sessions/cli/`) **e Kiro IDE**
(sessões em `~/.config/Kiro/User/globalStorage/kiro.kiroagent/`).

**Matriz de comportamento:**

| CLI | IDE | Modo | Recursos disponíveis |
|---|---|---|---|
| ✓ | ✓ | **Completo** | CLI + IDE somados; billing autoritativo via IDE; dedup interno; audit running confiável |
| ✓ | ✗ | **CLI-only** | Estimativa local de saldo; banner sugerindo IDE; audit running via lockfile |
| ✗ | ✓ | **IDE-only** | Billing autoritativo via IDE; sem audit running CLI; sem transcripts CLI |
| ✗ | ✗ | **Onboarding** | Hint para instalar Kiro CLI ou IDE |

**Default mudou:** comandos com flag `--source` (`recent`, `audit running`,
`session`) agora têm `--source all` como padrão. Usuários com **apenas
CLI** instalado não notam diferença (única fonte é CLI). Usuários com
ambos veem dados unificados sem flag explícita.

Para preservar comportamento da v0.6.x, passe `--source cli` explicitamente.

**Identidade composta** distingue sessões: `cli:<uuid>` para CLI raw,
`ide-sessions:<uuid>` para IDE. Snapshots v2 persistem essa distinção
por sessão. Snapshots v1 (pré-v0.7.0) são lidos transparentemente como
v2 em memória.

**Privacidade preservada em ambas as fontes.** Backend IDE é tão cego
quanto o CLI: nunca lê `actions[].input.content`,
`actions[].say.message`, `history[].message` ou `editorState`.

**Detalhes de arquitetura:**
[`docs/adr/0001-multi-backend-architecture.md`](docs/adr/0001-multi-backend-architecture.md).

---

## Stack e arquitetura

- **Python 3.12+** stdlib first
- **[`rich`](https://rich.readthedocs.io)** — output formatado
- **[`click`](https://click.palletsprojects.com)** — CLI
- **[`textual`](https://textual.textualize.io)** — TUI
- **[`mcp`](https://github.com/modelcontextprotocol/python-sdk)** — servidor MCP
- **[`tomli_w`](https://github.com/hukkin/tomli-w)** — escrita TOML

Sem JavaScript/Node, sem banco de dados, sem servidor web. Tudo é
arquivo local: `.json` (metadata Kiro), `.jsonl` (transcripts; lemos só
metadata de tool calls), `.lock` (PID), `.toml` (config), snapshots
JSON em `~/.local/share/kiro-dash/`.

**Parser stateless por padrão:** cada execução re-lê o disco. Cache
opcional acelera leituras repetidas. Snapshots persistem agregados
diários para queries históricas e cross-device merge.

**Clock injetável:** funções de janela aceitam kwarg `now: datetime |
None = None`. Habilita testes determinísticos timezone-safe (sem
`freezegun`), replay/snapshot histórico, auditoria reproduzível.

**Multi-host:** snapshots distinguem origem por hostname; queries
históricas somam todos os hosts do mesmo dia. Sync via rclone deixa
arquivos coexistirem no Drive sem conflito de filename.

Estrutura interna em `src/kiro_dash/`:

```
parser.py        # Lê .json e .lock, retorna Session/Turn/LockInfo
jsonl_parser.py  # Lê .jsonl, retorna ToolCall (nome + status + summary)
aggregator.py    # Agregações (modelo, agent, projeto, ciclo, janelas)
account.py       # whoami parsing
config.py        # TOML config (plan + aliases)
project.py       # Heurística project_label
snapshots.py     # Persistência diária + merge multi-host
history.py       # Reconstrução month_summary, year_summary, diff
cache.py         # Cache mtime+size do parser
sync.py          # Wrapper rclone
watchdog.py      # Detector running/stuck + kill
visual.py        # Helpers bar_inline + sparkline
mcp_server.py    # Servidor MCP (stdio)
cli.py           # Subcomandos Click
views/           # TUI Textual (App + 7 abas)
```

201+ testes pytest (parser, aggregator, snapshots, history, watchdog,
visual, MCP, CLI, TUI). Rodar:

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

---

## Licença

**Proprietary — uso pessoal de Leonardo Menzani.**

Repositório público para transparência e auditoria. Uso, redistribuição
ou modificação por terceiros não estão licenciados — entre em contato
para negociar.
