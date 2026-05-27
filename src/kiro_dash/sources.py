"""Detector runtime das fontes Kiro disponíveis (ADR-0001 §"Detector").

Enumera os backends conhecidos, marca os disponíveis e expõe lista
priorizada por capability. Os comandos do CLI e tools do MCP consultam
``Sources.detect()`` ao invés de instanciar backend específico, o que
mantém o domínio agnóstico de qual fonte realmente está presente no
ambiente do usuário.

Cenários de instalação cobertos (ADR-0001 §"Política de fallback"):

- CLI ✓, IDE ✓: ambos backends ativos, billing autoritativo do IDE
- CLI ✓, IDE ✗: modo CLI-only, estimativa local de saldo + banner
- CLI ✗, IDE ✓: modo IDE-only, sem audit running confiável
- CLI ✗, IDE ✗: onboarding, hint para instalar Kiro CLI
"""
from __future__ import annotations

from dataclasses import dataclass

from kiro_dash.backends import Backend, Capability
from kiro_dash.backends.cli_json import CliJsonBackend
from kiro_dash.backends.ide_sessions import IdeSessionBackend
from kiro_dash.backends.ide_state import IdeStateBackend


@dataclass(frozen=True, slots=True)
class Sources:
    """Conjunto de backends instanciados, com ``is_available()`` consultado.

    Construído via :meth:`detect`. Os campos podem ser ``None`` quando o
    backend correspondente não foi instanciado/detectado. ``cli_sqlite``
    permanece placeholder até implementação futura (Wave 7+).
    """

    cli_json: Backend | None
    ide_state: Backend | None
    ide_sessions: Backend | None = None
    cli_sqlite: Backend | None = None  # placeholder Wave 7+

    @classmethod
    def detect(
        cls,
        *,
        cli_json: Backend | None | type[None] = ...,  # type: ignore[assignment]
        ide_state: Backend | None | type[None] = ...,  # type: ignore[assignment]
        ide_sessions: Backend | None | type[None] = ...,  # type: ignore[assignment]
    ) -> "Sources":
        """Detecta backends disponíveis no ambiente atual.

        Parâmetros (todos opcionais, úteis em testes):

        - ``cli_json``, ``ide_state``, ``ide_sessions``: passe instância
          para forçar (ou ``None`` para marcar como ausente). ``...``
          (default) instancia com defaults e checa ``is_available()``.
        """
        # CLI JSON
        if cli_json is ...:  # type: ignore[comparison-overlap]
            candidate = CliJsonBackend()
            cli_json_resolved: Backend | None = candidate if candidate.is_available() else None
        else:
            cli_json_resolved = cli_json  # type: ignore[assignment]

        # IDE State
        if ide_state is ...:  # type: ignore[comparison-overlap]
            candidate_ide = IdeStateBackend()
            ide_state_resolved: Backend | None = candidate_ide if candidate_ide.is_available() else None
        else:
            ide_state_resolved = ide_state  # type: ignore[assignment]

        # IDE Sessions (Wave 6 frente Q)
        if ide_sessions is ...:  # type: ignore[comparison-overlap]
            candidate_sess = IdeSessionBackend()
            ide_sessions_resolved: Backend | None = (
                candidate_sess if candidate_sess.is_available() else None
            )
        else:
            ide_sessions_resolved = ide_sessions  # type: ignore[assignment]

        return cls(
            cli_json=cli_json_resolved,
            ide_state=ide_state_resolved,
            ide_sessions=ide_sessions_resolved,
        )

    def all_backends(self) -> list[Backend]:
        """Lista todos os backends presentes (não-``None``), em ordem fixa."""
        out: list[Backend] = []
        for b in (self.cli_json, self.ide_state, self.ide_sessions, self.cli_sqlite):
            if b is not None:
                out.append(b)
        return out

    def available_for(self, capability: Capability) -> list[Backend]:
        """Backends que fornecem ``capability``, em ordem de preferência.

        Ordem de preferência (ADR-0001 §"Política de seleção"):

        - ``USAGE_STATE``: ``ide_state`` (autoritativo) preferido
        - ``SESSIONS``/``TURNS``/``TOOL_CALLS``: união CLI + IDE (CLI primeiro)
        - ``RUNNING``: união (CLI tem confiabilidade via lockfile;
          IDE via execution.status=running no catálogo, decisão #10/Q)
        """
        if capability is Capability.USAGE_STATE:
            return [self.ide_state] if self.ide_state is not None else []

        ordered: list[Backend] = []
        for b in (self.cli_json, self.ide_sessions, self.cli_sqlite, self.ide_state):
            if b is not None and capability in b.capabilities():
                ordered.append(b)
        return ordered

    def has_any(self) -> bool:
        """``True`` se qualquer backend está disponível."""
        return bool(self.all_backends())

    def has_only_cli(self) -> bool:
        """``True`` se CLI está disponível mas nenhum backend IDE.

        Considera ambos ``ide_state`` E ``ide_sessions`` ausentes —
        usuário com IDE instalado mas state.vscdb stale (sem
        usageState) ainda tem ``ide_sessions`` se abriu o IDE alguma
        vez. Banner de onboarding só aparece quando IDE realmente
        não foi detectado em nenhuma das duas fontes.
        """
        return (
            self.cli_json is not None
            and self.ide_state is None
            and self.ide_sessions is None
        )

    def summary_lines(self) -> list[str]:
        """Linhas resumo para uso em ``whoami`` e debug.

        Cada linha:  ``"  <slug>      <symbol>  <hint>"``
        Símbolo: ``✓`` ativo, ``—`` inativo/futuro.

        Mantido para compatibilidade. Para output mais estruturado,
        use :meth:`summary_rows` (Wave 8).
        """
        from kiro_dash.freshness import format_age, freshness_for

        lines: list[str] = []

        # CLI JSON
        if self.cli_json is not None:
            lines.append(f"  cli            ✓  CliJsonBackend")
        else:
            lines.append(f"  cli            —  (não detectado: ~/.kiro/sessions/cli/)")

        # IDE State
        if self.ide_state is not None:
            age = self.ide_state.data_age()
            if age is not None:
                level = freshness_for(age)
                lines.append(
                    f"  ide-state      ✓  IdeStateBackend (snapshot {format_age(age)} atrás · {level.value})"
                )
            else:
                lines.append(f"  ide-state      ✓  IdeStateBackend")
        else:
            lines.append(f"  ide-state      —  (Kiro IDE não detectado)")

        # IDE Sessions (frente Q da Wave 6)
        if self.ide_sessions is not None:
            ws_count = 0
            try:
                ws_count = len(self.ide_sessions.list_workspaces())  # type: ignore[attr-defined]
            except (AttributeError, OSError):
                pass
            age = self.ide_sessions.data_age()
            if age is not None:
                level = freshness_for(age)
                ws_word = "workspace" if ws_count == 1 else "workspaces"
                lines.append(
                    f"  ide-sessions   ✓  IdeSessionBackend ({ws_count} {ws_word} · "
                    f"{format_age(age)} atrás · {level.value})"
                )
            else:
                lines.append(f"  ide-sessions   ✓  IdeSessionBackend")
        else:
            lines.append(f"  ide-sessions   —  (Kiro IDE sem sessões — abra-o para popular)")

        # CLI sqlite (watchlist)
        lines.append(f"  cli-sqlite     —  (watchlist; conversations_v2 vazia)")

        return lines

    def summary_rows(self) -> list[tuple[str, str, str, str]]:
        """Linhas estruturadas para tabela rich (Wave 8).

        Retorna lista de tuplas ``(slug, status_symbol, status_color, detalhe)``:

        - ``slug``: ``"cli"``, ``"ide-state"``, ``"ide-sessions"``, ``"cli-sqlite"``
        - ``status_symbol``: ``"✓"`` (ativo) ou ``"—"`` (inativo/futuro)
        - ``status_color``: cor rich para o symbol (``"green"``, ``"dim"``, level de freshness)
        - ``detalhe``: descrição com idade/contagem quando relevante
        """
        from kiro_dash.freshness import format_age, freshness_for

        rows: list[tuple[str, str, str, str]] = []

        # CLI JSON
        if self.cli_json is not None:
            rows.append(("cli", "✓", "green", "CliJsonBackend"))
        else:
            rows.append(
                (
                    "cli",
                    "—",
                    "dim",
                    "não detectado: ~/.kiro/sessions/cli/",
                )
            )

        # IDE State
        if self.ide_state is not None:
            age = self.ide_state.data_age()
            if age is not None:
                level = freshness_for(age)
                rows.append(
                    (
                        "ide-state",
                        "✓",
                        level.value,
                        f"IdeStateBackend (snapshot {format_age(age)} atrás · {level.value})",
                    )
                )
            else:
                rows.append(("ide-state", "✓", "green", "IdeStateBackend"))
        else:
            rows.append(("ide-state", "—", "dim", "Kiro IDE não detectado"))

        # IDE Sessions
        if self.ide_sessions is not None:
            ws_count = 0
            try:
                ws_count = len(self.ide_sessions.list_workspaces())  # type: ignore[attr-defined]
            except (AttributeError, OSError):
                pass
            age = self.ide_sessions.data_age()
            if age is not None:
                level = freshness_for(age)
                ws_word = "workspace" if ws_count == 1 else "workspaces"
                rows.append(
                    (
                        "ide-sessions",
                        "✓",
                        level.value,
                        f"IdeSessionBackend ({ws_count} {ws_word} · "
                        f"{format_age(age)} atrás · {level.value})",
                    )
                )
            else:
                rows.append(("ide-sessions", "✓", "green", "IdeSessionBackend"))
        else:
            rows.append(
                (
                    "ide-sessions",
                    "—",
                    "dim",
                    "Kiro IDE sem sessões — abra-o para popular",
                )
            )

        # CLI sqlite (watchlist)
        rows.append(("cli-sqlite", "—", "dim", "watchlist; conversations_v2 vazia"))

        return rows


# ── Coletor multi-source (Wave 6 frente R) ──────────────────────────


VALID_SOURCES = ("cli", "ide", "all")


def _dedupe_by_session_id(sessions: list) -> list:
    """Remove duplicatas mantendo a primeira ocorrência por ``session_id``.

    Como sessões CLI e IDE têm slugs distintos (``cli`` raw uuid vs
    ``ide-sessions:<uuid>``), colisão real entre fontes é impossível.
    Esta função é defensiva contra dupla leitura (mesma fonte
    enumerada duas vezes por engano) e contra futuras fontes que
    possam compartilhar UUIDs.
    """
    seen: set[str] = set()
    out: list = []
    for s in sessions:
        if s.session_id in seen:
            continue
        seen.add(s.session_id)
        out.append(s)
    return out


def collect_sessions(
    source: str = "all",
    *,
    sources: "Sources | None" = None,
    dedupe: bool = True,
) -> list:
    """Coleta sessões da(s) fonte(s) pedida(s).

    :param source: ``cli`` (só CLI), ``ide`` (só IDE), ou ``all``
        (concatena CLI + IDE).
    :param sources: instância de :class:`Sources` para usar; se
        ``None``, chama :meth:`Sources.detect` (detecção live).
    :param dedupe: quando ``True`` (default), remove duplicatas por
        ``session_id`` em modo ``all``. Sem efeito em ``cli``/``ide``
        puros (não há overlap real).

    Source inválido cai silenciosamente para ``cli`` (retro-compat).
    Importações lazy para evitar ciclos.
    """
    if source not in VALID_SOURCES:
        source = "cli"
    out: list = []
    if source in ("cli", "all"):
        from kiro_dash.parser import load_all_sessions

        out.extend(load_all_sessions())
    if source in ("ide", "all"):
        srcs = sources if sources is not None else Sources.detect()
        if srcs.ide_sessions is not None:
            out.extend(srcs.ide_sessions.list_sessions())
    if dedupe and source == "all":
        out = _dedupe_by_session_id(out)
    return out
