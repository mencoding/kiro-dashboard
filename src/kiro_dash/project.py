"""Heurística de mapeamento ``cwd → label de projeto``."""
from __future__ import annotations

import re
from pathlib import Path

_KNOWN_CATEGORIES = {"pessoal", "profissional", "institucional", "concluidos"}


def project_label(cwd: str | None) -> str:
    """Mapeia ``cwd`` para um label conceitual de projeto."""
    if not cwd:
        return "?"

    home = str(Path.home())

    # iris/projetos/<categoria>/<projeto>(/...)?
    m = re.match(
        rf"^{re.escape(home)}/iris/projetos/([^/]+)/([^/]+)(?:/.*)?$", cwd,
    )
    if m:
        cat, proj = m.group(1), m.group(2)
        if cat in _KNOWN_CATEGORIES:
            return f"{cat}/{proj}"

    # iris/projetos/normativos
    if cwd.startswith(f"{home}/iris/projetos/normativos"):
        return "iris-normativos"

    # iris/projetos/referencias
    if cwd.startswith(f"{home}/iris/projetos/referencias"):
        return "iris-referencias"

    # iris/projetos (raiz ou sem categoria reconhecida)
    if cwd == f"{home}/iris/projetos" or cwd.startswith(f"{home}/iris/projetos/"):
        return "iris-projetos"

    # iris/... (root ou outros subdirs)
    if cwd == f"{home}/iris" or cwd.startswith(f"{home}/iris/"):
        return "iris-geral"

    # Desenvolvimento/ifsp/<grupo>/<repo>(/...)?
    m = re.match(
        rf"^{re.escape(home)}/Desenvolvimento/ifsp/([^/]+)/([^/]+)(?:/.*)?$", cwd,
    )
    if m:
        return f"ifsp/{m.group(1)}/{m.group(2)}"

    # Desenvolvimento/<conta>/<repo>(/...)?
    m = re.match(
        rf"^{re.escape(home)}/Desenvolvimento/([^/]+)/([^/]+)(?:/.*)?$", cwd,
    )
    if m:
        return f"{m.group(1)}/{m.group(2)}"

    # nyx
    if cwd == f"{home}/nyx" or cwd.startswith(f"{home}/nyx/"):
        return "nyx"

    # outros paths sob HOME → caminho relativo
    if cwd.startswith(f"{home}/"):
        return cwd[len(home) + 1:]

    # literal
    return cwd
