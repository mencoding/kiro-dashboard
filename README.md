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

## Licença

Privado — uso pessoal de Leonardo Menzani.
