"""Cobertura da heurística project_label."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from kiro_dash.project import project_label


@pytest.fixture
def home(tmp_path: Path):
    """Substitui Path.home() por tmp_path durante o teste."""
    with patch.object(Path, "home", return_value=tmp_path):
        yield tmp_path


def test_iris_projetos_categoria_projeto(home):
    cwd = str(home / "iris/projetos/institucional/auto-normas")
    assert project_label(cwd) == "institucional/auto-normas"


def test_iris_projetos_categoria_projeto_subpasta(home):
    cwd = str(home / "iris/projetos/institucional/auto-normas/workspace")
    assert project_label(cwd) == "institucional/auto-normas"


def test_iris_projetos_categoria_geral_sub(home):
    cwd = str(home / "iris/projetos/institucional/geral")
    assert project_label(cwd) == "institucional/geral"


def test_iris_projetos_pessoal(home):
    cwd = str(home / "iris/projetos/pessoal/docente-ifsp")
    assert project_label(cwd) == "pessoal/docente-ifsp"


def test_iris_projetos_concluidos(home):
    cwd = str(home / "iris/projetos/concluidos/normas-centralizadas")
    assert project_label(cwd) == "concluidos/normas-centralizadas"


def test_iris_normativos(home):
    cwd = str(home / "iris/projetos/normativos")
    assert project_label(cwd) == "iris-normativos"


def test_iris_normativos_subdir(home):
    cwd = str(home / "iris/projetos/normativos/ifsp")
    assert project_label(cwd) == "iris-normativos"


def test_iris_referencias(home):
    cwd = str(home / "iris/projetos/referencias/info-pessoal")
    assert project_label(cwd) == "iris-referencias"


def test_iris_projetos_sem_categoria_reconhecida(home):
    cwd = str(home / "iris/projetos")
    assert project_label(cwd) == "iris-projetos"


def test_iris_geral_root(home):
    cwd = str(home / "iris")
    assert project_label(cwd) == "iris-geral"


def test_iris_geral_outras_pastas(home):
    cwd = str(home / "iris/audit")
    assert project_label(cwd) == "iris-geral"


def test_dev_pessoal_padrao(home):
    cwd = str(home / "Desenvolvimento/mencoding/kiro-dash")
    assert project_label(cwd) == "mencoding/kiro-dash"


def test_dev_pessoal_subdir(home):
    cwd = str(home / "Desenvolvimento/mencoding/kiro-dash/.worktrees/x")
    assert project_label(cwd) == "mencoding/kiro-dash"


def test_dev_ifsp_3_niveis(home):
    cwd = str(home / "Desenvolvimento/ifsp/incubadora/projeto-x")
    assert project_label(cwd) == "ifsp/incubadora/projeto-x"


def test_nyx(home):
    cwd = str(home / "nyx")
    assert project_label(cwd) == "nyx"


def test_nyx_subdir(home):
    cwd = str(home / "nyx/memory")
    assert project_label(cwd) == "nyx"


def test_path_fora_de_padrao_devolve_relativo_ao_home(home):
    cwd = str(home / "outras-coisas/path-x")
    assert project_label(cwd) == "outras-coisas/path-x"


def test_path_completamente_fora_do_home_devolve_literal():
    assert project_label("/tmp/coisa") == "/tmp/coisa"


def test_cwd_vazio_retorna_interrogacao():
    assert project_label("") == "?"


def test_cwd_none_safe():
    assert project_label(None) == "?"  # type: ignore[arg-type]


def test_alias_vence_heuristica(home):
    cwd = str(home / "iris/projetos/institucional/auto-normas")
    aliases = {str(home / "iris/projetos/institucional/auto-normas"): "auto-normas-custom"}
    assert project_label(cwd, aliases=aliases) == "auto-normas-custom"


def test_alias_match_por_prefixo(home):
    cwd = str(home / "lab/exp-001/sub")
    aliases = {str(home / "lab"): "experimentos"}
    assert project_label(cwd, aliases=aliases) == "experimentos"


def test_alias_mais_especifico_vence(home):
    cwd = str(home / "lab/exp-001/data")
    aliases = {
        str(home / "lab"): "experimentos",
        str(home / "lab/exp-001"): "exp-001",
    }
    assert project_label(cwd, aliases=aliases) == "exp-001"


def test_alias_vazio_devolve_heuristica(home):
    cwd = str(home / "nyx/memory")
    assert project_label(cwd, aliases={}) == "nyx"
    assert project_label(cwd, aliases=None) == "nyx"


def test_home_puro_vira_home(home):
    assert project_label(str(home)) == "home"


def test_downloads_documents_desktop_fallback(home):
    assert project_label(str(home / "Downloads")) == "home/Downloads"
    assert project_label(str(home / "Documents/x")) == "home/Documents"
    assert project_label(str(home / "Desktop")) == "home/Desktop"
