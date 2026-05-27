"""Heurística de mapeamento ``cwd → label de projeto``."""
from __future__ import annotations

import re
from pathlib import Path

_KNOWN_CATEGORIES = {"pessoal", "profissional", "institucional", "concluidos"}


def project_label(
    cwd: str | None,
    *,
    aliases: dict[str, str] | None = None,
) -> str:
    """Mapeia ``cwd`` para um label conceitual de projeto.

    Ordem: aliases (longest-prefix) → heurística → fallback.
    """
    if not cwd:
        return "?"

    # 1. Aliases — match por prefixo (longest match wins)
    if aliases:
        sorted_aliases = sorted(aliases.items(), key=lambda kv: -len(kv[0]))
        for alias_path, label in sorted_aliases:
            if cwd == alias_path or cwd.startswith(alias_path.rstrip("/") + "/"):
                return label

    # 2. Heurística hardcoded
    home = str(Path.home())

    # iris/projetos/<categoria>/<projeto>(/...)?
    m = re.match(
        rf"^{re.escape(home)}/iris/projetos/([^/]+)/([^/]+)(?:/.*)?$", cwd,
    )
    if m:
        cat, proj = m.group(1), m.group(2)
        if cat in _KNOWN_CATEGORIES:
            return f"{cat}/{proj}"

    if cwd.startswith(f"{home}/iris/projetos/normativos"):
        return "iris-normativos"
    if cwd.startswith(f"{home}/iris/projetos/referencias"):
        return "iris-referencias"
    if cwd == f"{home}/iris/projetos" or cwd.startswith(f"{home}/iris/projetos/"):
        return "iris-projetos"
    if cwd == f"{home}/iris" or cwd.startswith(f"{home}/iris/"):
        return "iris-geral"

    m = re.match(
        rf"^{re.escape(home)}/Desenvolvimento/ifsp/([^/]+)/([^/]+)(?:/.*)?$", cwd,
    )
    if m:
        return f"ifsp/{m.group(1)}/{m.group(2)}"

    m = re.match(
        rf"^{re.escape(home)}/Desenvolvimento/([^/]+)/([^/]+)(?:/.*)?$", cwd,
    )
    if m:
        return f"{m.group(1)}/{m.group(2)}"

    if cwd == f"{home}/nyx" or cwd.startswith(f"{home}/nyx/"):
        return "nyx"

    # 3. HOME puro e subpastas comuns
    if cwd == home:
        return "home"
    for sub in ("Downloads", "Documents", "Desktop"):
        if cwd == f"{home}/{sub}" or cwd.startswith(f"{home}/{sub}/"):
            return f"home/{sub}"

    # Outros paths sob HOME
    if cwd.startswith(f"{home}/"):
        return cwd[len(home) + 1:]

    return cwd
