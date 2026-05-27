# ADR-0001 — Multi-backend architecture para suporte a Kiro CLI + Kiro IDE

- **Status:** Accepted
- **Data:** 2026-05-27
- **Autores:** Leonardo Menzani, Nyx
- **Versão alvo:** v0.7.0 (Wave 6)
- **Supersede:** —

## Contexto

Até a v0.6.1, o `kiro-dash` lê exclusivamente os artefatos do **Kiro CLI**:

- `~/.kiro/sessions/cli/<sid>.json` — metadata da sessão e turns
- `~/.kiro/sessions/cli/<sid>.jsonl` — eventos de tool call
- `~/.kiro/sessions/cli/<sid>.lock` — PID da sessão em execução

Essa fonte traz consumo de créditos por turn (`metering_usage[]`),
modelo, agent, projeto (cwd), tool calls e estado live de sessões. É
suficiente para os comandos atuais (`today`, `projects`, `models`,
`tools`, `audit`, `balance`).

Investigação realizada em 2026-05-27 sobre fontes adicionais
(item da Wave 5 overview "Investigar `~/.local/share/kiro-cli/data.sqlite3`
como fonte adicional") revelou:

1. **`~/.local/share/kiro-cli/data.sqlite3` está vazio para conversação.**
   As tabelas `conversations` e `conversations_v2` existem com schema
   completo (chave por diretório + UUID + JSON + timestamps em ms) mas
   não recebem dados na versão atual do CLI. As 9 entradas em `state`
   são auth/telemetry; `history` é shell history (vazia, opt-in).
   Conclusão: infra preparatória do CLI para storage futuro, sem valor
   imediato.

2. **Kiro IDE (fork de VS Code, Electron) tem storage próprio e rico.**
   Identificadas três fontes inéditas:

   a. **Billing autoritativo do servidor** em
      `~/.config/Kiro/User/globalStorage/state.vscdb`, chave
      `kiro.kiroAgent` no `ItemTable`. Campo
      `kiro.resourceNotifications.usageState` carrega `currentUsage`,
      `usageLimit`, `percentageUsed`, `currentOverages`, `overageCap`,
      `overageRate`, `resetDate`, `currency` e `timestamp` (ms). É
      atualizado em background (≈30-60s) enquanto o IDE roda, refletindo
      consumo **global da conta** (CLI + IDE + Web), não apenas o que o
      IDE local executou.

   b. **Sessões de chat do IDE** em
      `~/.config/Kiro/User/globalStorage/kiro.kiroagent/workspace-sessions/<base64url(workspace_path)>/`,
      com catálogo `sessions.json` e arquivos `<sid>.json` por sessão.
      Schema próprio (campos `history`, `autonomyMode`, `selectedModel`,
      `sessionType`, `contextUsagePercentage`).

   c. **Arquivos de execução** em
      `~/.config/Kiro/User/globalStorage/kiro.kiroagent/<profile_hash>/<action_hash>/<exec_hash>.json`,
      com créditos por turn em `usageSummary[]`, classificação de intent
      (`localIntent` heurística + `llmIntent` do classifier),
      `workflowType` (`chat-agent`/`do-agent`/`spec`) e `actions[]` (tool
      calls e fases internas do turn).

3. **Distintos cenários de instalação observáveis em campo.** O usuário
   pode ter:
   - apenas CLI (cenário atual da maioria dos devs)
   - apenas IDE
   - ambos (caso mais rico, mas precisa cuidar de duplicidade)
   - nenhum (kiro-dash sem dados — situação possível ao instalar antes do
     Kiro)

A arquitetura monolítica atual (parser direto sobre CLI) não acomoda
essa diversidade sem refactor.

## Decisão

Adotar arquitetura **multi-backend com detector de fontes em runtime**.

### Modelo de fontes

Cada fonte é encapsulada num backend que implementa uma interface
comum. Quatro fontes nomeadas:

| Identificador | Caminho | Tipo | Status |
|---|---|---|---|
| `CliJsonBackend` | `~/.kiro/sessions/cli/*.{json,jsonl,lock}` | filesystem | atual (renomeado a partir do parser monolítico) |
| `IdeStateBackend` | `~/.config/Kiro/User/globalStorage/state.vscdb` | sqlite read-only | novo (frente P) |
| `IdeSessionBackend` | `~/.config/Kiro/User/globalStorage/kiro.kiroagent/{workspace-sessions,<profile_hash>}/` | filesystem | novo (frente Q) |
| `CliSqliteBackend` | `~/.local/share/kiro-cli/data.sqlite3` | sqlite read-only | watchlist — implementar quando `conversations_v2` começar a popular |

Cada backend declara:

- **Capabilities:** quais conceitos fornece (`sessions`, `turns`,
  `tool_calls`, `running`, `usage_state`)
- **Disponibilidade:** método `is_available()` que faz check leve
  (existe path? schema versionado conhecido?)
- **Frescor:** método `data_age()` que retorna idade do dado mais recente
  ou `None` se irrelevante (ex: `CliJsonBackend` não tem age — é live)

### Detector

Componente novo `sources.py` enumera os backends, marca disponíveis e
expõe lista priorizada por capability. Comandos do CLI e tools do MCP
consultam o detector ao invés de instanciar backend específico.

### Política de seleção por capability

| Capability | Preferência | Fallback | Comportamento se nenhuma fonte |
|---|---|---|---|
| `usage_state` (saldo autoritativo) | `IdeStateBackend` | estimativa local via `CliJsonBackend` + plan config | erro `no usage source available` |
| `sessions`, `turns`, `tool_calls` | união (`CliJsonBackend` ∪ `IdeSessionBackend`) | a fonte disponível | aviso `no Kiro installation detected` |
| `running` (sessões em curso) | união dos dois | a fonte disponível | lista vazia |
| `account_info` | `IdeStateBackend.profile.json` se IDE; `CliJsonBackend.account` se CLI | — | erro `not authenticated` |

### Identidade de sessão composta

Para evitar colisão entre fontes e remover ambiguidade na
deduplicação, o `kiro-dash` usa identidade interna composta:

```
internal_session_id := "<source_slug>:<source_session_id>"
```

Slugs reservados:

| Backend | Slug |
|---|---|
| `CliJsonBackend` | `cli` |
| `IdeSessionBackend` | `ide` |
| `CliSqliteBackend` | `cli-sqlite` (futuro) |

Exemplo: `cli:8e2c534f-0296-4bc8-9048-196ca3521378` e
`ide:8e2c534f-0296-4bc8-9048-196ca3521378` são identificadores
**distintos** mesmo se o UUID coincidir. Não há "fonte vencedora": as
duas sessões aparecem em listagens, com a coluna `source` exibindo o
slug.

O slug é detalhe interno: o `session_id` exposto ao usuário em
comandos como `kiro-dash session <prefix>` continua aceitando o UUID
nativo. Quando houver ambiguidade real (mesmo prefixo em duas fontes),
o CLI exibe as duas opções com slug e pede desambiguação.

Em arquivos de snapshot, cache e MCP, o campo passa a ser
`internal_session_id`. Migração de snapshots antigos é detalhada na
seção [Estratégia de migração e backfill](#estratégia-de-migração-e-backfill).

## Alternativas consideradas

### A. Parser unificado autodetectando formato no mesmo módulo

Manter `parser.py` único e ramificar internamente conforme detectar
`.json` ou `state.vscdb`. **Rejeitada** porque acopla schemas externos
no mesmo arquivo: cada update do CLI ou do IDE força edição num único
ponto sensível, com risco de regressão cruzada. Viola separação de
fronteira que protege o domínio do dashboard de mudanças downstream.

### B. Projeto separado (`kiro-ide-dash` ao lado de `kiro-dash`)

Criar pacote independente para o IDE. **Rejeitada** porque:

- Duplica TUI, MCP server, queries históricas e snapshots
- Usuário com ambos teria dois dashboards a abrir
- Manutenção dobrada sem ganho arquitetural — backends já isolam o
  necessário

### C. Leitura via API web do Kiro

Consumir `app.kiro.dev` ou endpoints internos. **Rejeitada** porque:

- Não há API pública documentada para uso de billing/sessões
- Login institucional via SSO inviabiliza fluxo headless local
- Latência de rede em comando de terminal local é regressão de UX
- Privacidade: kiro-dash hoje é offline-first; manter

### D. Esperar o Kiro CLI popular `conversations_v2` no sqlite e ler de lá

Adiar suporte ao IDE até o CLI consolidar storage. **Rejeitada**
porque o IDE já existe, traz dado autoritativo de billing **agora** e
adiar significa estimativa local imprecisa por meses. A frente
`CliSqliteBackend` fica em watchlist sem bloquear a Wave 6.

## Consequências

### Positivas

- **Isolamento por adapter:** schema do CLI ou do IDE muda → só o
  adapter correspondente é afetado, com fixtures versionadas no
  `tests/fixtures/`
- **Extensibilidade:** novas fontes (Kiro Web cache, Kiro plugin do
  JetBrains, etc.) entram como backend novo, sem reformar o aggregator
- **Fallback gracioso:** instalações parciais (só CLI ou só IDE) são
  cidadãos de primeira classe; usuário recebe degradação previsível, não
  crashes
- **Billing autoritativo:** `kiro-dash balance` deixa de ser estimativa
  e passa a refletir o servidor; resolve a nota de imprecisão no README
  atual
- **Frescor explícito:** badge de idade do dado evita decisão errada com
  base em snapshot velho
- **Visão global da conta:** quando IDE está aberto, billing reflete
  consumo de qualquer cliente Kiro da conta (CLI, IDE, Web), eliminando
  drift entre dispositivos

### Negativas

- **Superfície de código maior:** `~3 backends + sources detector +
  aggregator multi-source` em vez de parser único; testes crescem
  proporcionalmente
- **Schemas externos não-documentados:** Kiro CLI e IDE não publicam
  contrato de storage; mudanças entre versões podem quebrar adapters
  sem aviso prévio
- **Identidade composta força refatoração:** `session_id` deixa de ser
  a chave única do domínio; código existente que assume UUID puro
  precisa adotar `internal_session_id`. Snapshots antigos exigem
  fallback de compatibilidade
- **Histórico IDE pré-Wave-6 só vira observável sob demanda:** sessões
  IDE de >30 dias atrás (fora da janela self-healing) entram apenas
  quando o usuário consultar especificamente aquele dia via `today --day`
  ou navegação na TUI; primeira consulta pode ser mais lenta por
  exigir varredura completa do dia em ambas as fontes
- **Frescor em billing pode iludir:** badge antigo é informação, não
  garantia de que o saldo está errado — usuário precisa entender a
  semântica

### Mitigações para as negativas

- Cada adapter testa schema contra `PRAGMA user_version` (sqlite) ou
  `version` declarado no JSON; falha cedo com mensagem clara em vez de
  silenciar
- CI roda fixtures de schemas conhecidos; quando aparece versão nova
  em campo, o erro carrega o `version` observado para reporte rápido
- Documentação do README e do output do `whoami`/`balance` deixa
  explícito quais fontes estão ativas e qual a idade do dado de cada uma

## Princípio operacional

`kiro-dash` **só lê** os storages do Kiro CLI/IDE. Nunca escreve,
nunca altera, nunca aciona migrations. Operacionalmente:

- sqlite: aberto com `?mode=ro&immutable=0` (read-only com possibilidade
  do CLI/IDE escreverem em paralelo); retry com backoff em
  `SQLITE_BUSY`
- filesystem: arquivos abertos `O_RDONLY`; sem locks competindo
- Detecção: nunca tocar em diretórios de auth (`auth_kv`, tokens,
  credenciais cognito); leitura limitada às chaves listadas neste ADR

Esse princípio é diretiva forte: violação deve ser flagged em code
review como bloqueante.

## Política de fallback (matriz CLI × IDE)

| CLI | IDE | Comportamento |
|---|---|---|
| ✓ | ✓ | Modo completo. Todas as capabilities; deduplicação por `session_id`; billing do IDE preferido |
| ✓ | ✗ | Modo CLI-only (atual). `balance` exibe estimativa local + warning *"instale o Kiro IDE para saldo autoritativo"*. Banner sugere instalação na primeira execução |
| ✗ | ✓ | Modo IDE-only. Sem `audit running/stuck` (sem lockfile por sessão IDE), sem agents diferenciados; `balance` autoritativo |
| ✗ | ✗ | Modo onboarding. `whoami` retorna *"no Kiro installation detected"* com hint para `curl -fsSL https://cli.kiro.dev/install \| bash` |

A detecção é re-executada a cada invocação do CLI/MCP — instalar o IDE
após o `kiro-dash` é detectado na próxima execução sem precisar de
reset.

## Política de frescor (idade do dado)

Cada backend que carrega dado cacheado externamente declara `data_age()`.
Para `IdeStateBackend.usage_state`, a idade é
`now() - timestamp_ms`. Convenções de exibição:

| Idade | Tratamento visual | Mensagem |
|---|---|---|
| < 3 h | verde, sem mensagem | (nenhuma) |
| 3 h – 12 h | amarelo | `snapshot de Xh atrás` |
| 12 h – 24 h | vermelho | `snapshot de Xh atrás — abra o Kiro IDE para refresh` |
| ≥ 24 h | cinza | `snapshot stale (Xd) — saldo pode estar muito desatualizado` |

Justificativa da ordem (cinza para o caso mais grave): cor cinza
sinaliza "fora de operação útil" — a partir desse ponto o dado tem
baixo valor decisório e o usuário deve tratar como inexistente,
diferente de vermelho (alarme presente, mas dado ainda é referência).

A idade é exibida em `balance`, `plan get`, no card de saldo da TUI e
no MCP `usage_state` (campo `data_age_seconds`).

## Estratégia de migração e backfill

### Cenários de instalação

| Cenário | Snapshots existentes | Dados IDE acumulados | Comportamento na v0.7.0 |
|---|---|---|---|
| **A.** v0.6.x → v0.7.0, CLI-only | sim, schema v1 (sem slug) | nenhum | Reader injeta `cli:` em todas as sessões; nada extra a fazer |
| **B.** v0.6.x → v0.7.0, IDE pré-existente | sim, schema v1 | sim, em arquivos do IDE | Reader injeta `cli:` em snapshots antigos; histórico IDE entra via lazy on-demand quando usuário consultar dias passados |
| **C.** Instalação fresh na v0.7.0 | nenhum | qualquer | Sem retrocompat necessária; self-healing varre janela inicial e gera snapshots já em v2 |
| **D.** Cross-device, devices em versões diferentes | mistos no Drive | qualquer | v0.7.0 escreve v2; v0.6.x ignora campos extras (`schema_version`, `internal_session_id`, `source`) — forward-compat JSON; recomendar update sincronizado |

### Premissa fundamental

Snapshot pré-v0.7.0 sem slug é **necessariamente** uma agregação
exclusiva de sessões CLI. v0.6.x não possui leitor de IDE, portanto é
impossível um snapshot antigo conter sessão IDE. A atribuição
retroativa de `cli:` é matematicamente correta, não suposição.

### Schema bump v1 → v2

```json
// v1 (kiro-dash v0.6.x)
{
  "sessions": [
    {"session_id": "8e2c534f-...", "model": "...", "credits": 12.5}
  ]
}

// v2 (kiro-dash v0.7.0)
{
  "schema_version": 2,
  "sessions": [
    {
      "internal_session_id": "cli:8e2c534f-...",
      "source": "cli",
      "session_id": "8e2c534f-...",
      "model": "...",
      "credits": 12.5
    }
  ]
}
```

### Mecanismos de migração — apenas self-healing + lazy

A migração não tem comando dedicado (sem `migrate`, sem `--backfill`).
Ela emerge da combinação de dois mecanismos já presentes na arquitetura:

1. **Carregamento transparente.** Ao ler snapshot v1, o reader detecta
   ausência de `schema_version` e injeta `source: "cli"` +
   `internal_session_id: "cli:<uuid>"` em memória. A próxima escrita
   do mesmo dia (que aconteceria por self-healing ou nova execução)
   grava em formato v2.

2. **Self-healing 30 dias** (Wave 5, já existente). Cada execução
   verifica buracos nos últimos 30 dias e gera snapshots faltantes
   lendo todas as fontes disponíveis. Após upgrade para v0.7.0, isso
   captura automaticamente sessões IDE dos últimos 30 dias.

3. **Lazy on-demand para histórico longo** (Wave 5, já existente).
   Comandos como `kiro-dash today --day 2026-01-15` ou navegação na
   TUI History acionam geração sob demanda do dia consultado. O gerador
   v0.7.0 lê **todas as fontes disponíveis naquela data** (`.json` do
   CLI + `workspace-sessions/` do IDE + execution files do IDE),
   produzindo snapshot v2 completo. Cache-amortizado: segunda consulta
   do mesmo dia já lê o snapshot pronto.

### Política cross-device

Snapshots v2 carregam campos extras (`schema_version`,
`internal_session_id`, `source`) que readers v0.6.x ignoram
silenciosamente — comportamento padrão de JSON parsing. Logo, um
device em v0.7.0 sincronizando com outro em v0.6.x não quebra o lado
antigo, mas o lado antigo perde a distinção CLI/IDE.

Recomendação: atualizar todos os devices em janela curta (mesma
semana). Não há quebra hard, mas o ganho de visibilidade só aparece
após update geral.

## Notas de privacidade

O IDE traz campos **a mais** que o CLI:

- `intentResult` (chat/do/spec scores)
- `actions[].actionType` (intent, chat, tool, contextLoad, etc.)
- `usageSummary[]` (créditos por workflow type)
- `dev_data/tokens_generated.jsonl` (model, provider, promptTokens, generatedTokens)

Política reforçada: `IdeSessionBackend` lê **apenas metadata
estrutural** desses arquivos. Conteúdo de mensagens (campos `text`,
`content`, `message`, `body`, `prompt`, `response`, `rendered`,
`thinking`) **não entra** em índice, cache, snapshot, MCP ou logs do
kiro-dash. Mantida a postura do parser CLI atual.

A regra `KIRO_DASH_ALLOW_CONTENT=1` (planejada para v0.8.0) seria a
única forma futura de habilitar leitura de conteúdo, com aviso
explícito e documentação de risco.

## Referências cruzadas

- Plano da Wave 6: `docs/superpowers/plans/2026-05-28-wave6-overview.md`
  (a criar)
- Frentes:
  - P (`IdeStateBackend` para billing): `2026-05-28-wave6-ide-state.md`
  - Q (`IdeSessionBackend` para sessões): `2026-05-28-wave6-ide-sessions.md`
  - R (unificação CLI+IDE em queries): `2026-05-28-wave6-unification.md`
- Schemas observados (samples redatadas em `tests/fixtures/ide/`):
  - `state_vscdb_kiroagent.json` — exemplo do `kiro.kiroAgent.usageState`
  - `workspace_sessions_index.json` — catálogo `sessions.json`
  - `workspace_session.json` — sessão completa redatada
  - `execution.json` — arquivo de execução redatado
- Storage do Kiro CLI: `parser.py` (já existe), `jsonl_parser.py`
- Documentação oficial:
  - https://kiro.dev/docs/cli/chat/session-management/
  - https://kiro.dev/ (downloads do IDE)

## Histórico

| Data | Versão | Mudança |
|---|---|---|
| 2026-05-27 | 1.0 | Versão inicial — decisão tomada após investigação de storage IDE |
