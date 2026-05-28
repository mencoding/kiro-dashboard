# ADR-0002: Filename de execution blob é storage-key opaca

**Status:** Aceita
**Data:** 2026-05-27
**Sprint:** Wave 9 (v0.7.3)

## Contexto

O Kiro IDE persiste cada execution (turn de chat-agent ou
spec-generation) como um arquivo JSON dentro de:

```
~/.config/Kiro/User/globalStorage/kiro.kiroagent/<account_hash>/<inner_dir>/<filename>
```

Em versões anteriores do Kiro IDE, o `<filename>` correspondia ao
`executionId` em formato UUID (8-4-4-4-12 com hífens). O
`IdeSessionBackend` da Wave 6 (frente Q) implementou a regex
`_EXECUTION_ID_RE = ^[a-f0-9]{8}-[a-f0-9]{4}-...$` como pré-filtro
de I/O — identificada no code review como I7
("evitar I/O wasteful em arquivos auxiliares").

Em versões atuais (observado em 2026-05-27, Predator-PH315-54), o
Kiro IDE passou a usar **outro identificador como nome do arquivo**:
um string de 32 hexadecimais sem hífens. Investigação confirmou que
**não é hash MD5/SHA1 do executionId** — é uma chave de storage
opaca, presumivelmente derivada de outro campo interno (storage
layer ou mapeamento backend).

O conteúdo JSON dentro do blob **continua tendo `executionId` em
formato UUID** com hífens. Apenas o nome do arquivo mudou.

Sintoma observado:
- `IdeSessionBackend.list_sessions()` retornava 1 sessão (correto:
  workspace-sessions ainda válido) com 0 turns.
- O scanner `_scan_all_executions` rejeitava todos os blobs porque
  os nomes não casavam com a regex de UUID.
- Resultado: créditos IDE não apareciam em `kiro-dash today`,
  `recent`, `tools` etc.

## Decisão

A regex `_EXECUTION_ID_RE` aceita **dois formatos**:

```python
_EXECUTION_ID_RE = re.compile(
    r"^([a-f0-9]{32}|[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})$"
)
```

A regex permanece como **pré-filtro de I/O** — não é uma garantia
semântica. A função `read_execution()` decide schema:
arquivos que passam o regex mas falham parse JSON ou não têm
campos esperados retornam `None` e são silenciosamente ignorados
pelo iter.

O nome do arquivo **não é tratado como portador de identidade
semântica**. O `executionId` interno (no JSON) é a verdade.
`chat_session_id` (no JSON) é o que agrupa executions em sessões.

## Alternativas consideradas

### A. Usar o catálogo (`f62de366...`) como fonte de verdade

Listar executionIds do catálogo e procurar arquivos correspondentes.
**Rejeitado:** o nome do arquivo não é função do executionId
(testado MD5/SHA1, não bate). Não há mapeamento determinístico
catálogo→arquivo sem abrir cada blob para confirmar.

### B. Tentar parser cada arquivo regular

Sem pré-filtro, abrir todos os arquivos e ver se parse como JSON
de execution. **Rejeitado:** I/O wasteful em arquivos auxiliares
(catalog index, profile.json, eventuais arquivos futuros). I7 do
code review original ainda vale.

### C. Aceitar qualquer filename que pareça hash hex

Regex como `^[a-f0-9]{16,64}$`. **Rejeitado:** muito permissivo;
falsos positivos em uma instalação com debris ou layout não
documentado seriam silenciosos. O par UUID|hex32 cobre os dois
formatos observados em produção.

## Consequências

### Positivas

- Suporta tanto instalações novas (hex32) quanto antigas (UUID)
  sem migração de schema.
- Robust contra mudanças futuras do storage layer: se o IDE mudar
  para outro formato de filename, basta estender a regex.
- Mantém pré-filtro de I/O barato (regex match O(1)).
- `read_execution()` continua sendo a única autoridade sobre
  validade semântica.

### Negativas / Pontos de atenção

- A regex é um pré-filtro, não um schema validator. Auditores que
  lerem o código devem entender que o **nome do arquivo é storage
  detail**; o conteúdo JSON é o que interessa.
- Se o IDE introduzir um terceiro formato (ex.: SHA-256 = 64 hex
  chars), o backend vai precisar de update.
- Catalog index (`f62de366...`, hex32 válido) tecnicamente passa
  a regex — mas a discriminação acontece no nível de hierarquia
  (`iter_profile_hash_dirs` o trata como arquivo no parent, nunca
  desce nele).

## Sinais de erosão

- Filename de execution em formato não cobertO pela regex
  → `_scan_all_executions` retorna vazio silenciosamente
  → `today`/`tools` mostram 0 turns IDE.
- **Sintoma de detecção precoce:** `kiro-dash whoami` mostra
  `ide-sessions ✓ (N workspaces)` mas `today` ignora IDE.
- **Defesa:** novos formatos devem ser adicionados explicitamente
  na regex com teste regressivo em `tests/test_ide_filename_regex.py`.

## Tests regressivos

`tests/test_ide_filename_regex.py` cobre:

- 6 filenames válidos parametrizados (3 UUID + 3 hex32).
- 9 filenames inválidos (auxiliares, comprimentos errados, chars
  inválidos, vazio).
- 3 testes de integração com fixtures montando layout completo:
  hex32-only, UUID-only, mix de auxiliares.
- 1 teste defensivo: blob inválido não vira Turn mesmo passando
  o regex.

## Referências

- `src/kiro_dash/backends/ide_sessions.py` — `_EXECUTION_ID_RE`,
  `_scan_all_executions`, `read_execution`.
- `docs/superpowers/plans/2026-05-28-wave6-ide-sessions.md`
  frente Q — implementação original do backend.
- ADR-0001 — multi-backend architecture.
- CHANGELOG.md `[0.7.3]` — release com este fix.
