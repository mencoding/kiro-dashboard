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

from dataclasses import dataclass, field

from kiro_dash.backends import Backend, Capability
from kiro_dash.backends.cli_json import CliJsonBackend
from kiro_dash.backends.ide_state import IdeStateBackend


@dataclass(frozen=True, slots=True)
class Sources:
    """Conjunto de backends instanciados, com ``is_available()`` consultado.

    Construído via :meth:`detect`. Os campos podem ser ``None`` quando o
    backend correspondente não foi instanciado (ex.: cli_sqlite/ide_sessions
    ainda não implementados nas frentes Q/R).
    """

    cli_json: Backend | None
    ide_state: Backend | None
    # Placeholders para frentes Q/R; sempre None até implementação:
    cli_sqlite: Backend | None = None
    ide_sessions: Backend | None = None

    @classmethod
    def detect(
        cls,
        *,
        cli_json: Backend | None | type[None] = ...,  # type: ignore[assignment]
        ide_state: Backend | None | type[None] = ...,  # type: ignore[assignment]
    ) -> "Sources":
        """Detecta backends disponíveis no ambiente atual.

        Parâmetros (todos opcionais, úteis em testes):

        - ``cli_json``, ``ide_state``: passe instância para forçar (ou
          ``None`` para marcar como ausente). ``...`` (default) instancia
          com defaults e checa ``is_available()``.
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

        return cls(
            cli_json=cli_json_resolved,
            ide_state=ide_state_resolved,
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
        - ``RUNNING``: união (mas só CLI tem confiabilidade hoje)
        """
        if capability is Capability.USAGE_STATE:
            ordered: list[Backend] = []
            if self.ide_state is not None:
                ordered.append(self.ide_state)
            return [b for b in ordered if capability in b.capabilities()]

        # Para SESSIONS/TURNS/TOOL_CALLS/RUNNING/ACCOUNT, união com CLI
        # primeiro. As frentes Q/R adicionam IDE_SESSIONS aqui.
        ordered = []
        for b in (self.cli_json, self.ide_sessions, self.cli_sqlite, self.ide_state):
            if b is not None and capability in b.capabilities():
                ordered.append(b)
        return ordered

    def has_any(self) -> bool:
        """``True`` se qualquer backend está disponível."""
        return bool(self.all_backends())

    def has_only_cli(self) -> bool:
        """``True`` se CLI está disponível mas IDE não.

        Usado para decidir exibir banner de onboarding sugerindo IDE.
        """
        return self.cli_json is not None and self.ide_state is None

    def summary_lines(self) -> list[str]:
        """Linhas resumo para uso em ``whoami`` e debug.

        Cada linha:  ``"  <slug>      <symbol>  <hint>"``
        Símbolo: ``✓`` ativo, ``—`` inativo/futuro.
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
        lines.append(f"  ide-sessions   —  (frente Q da Wave 6)")

        # CLI sqlite (watchlist)
        lines.append(f"  cli-sqlite     —  (watchlist; conversations_v2 vazia)")

        return lines
