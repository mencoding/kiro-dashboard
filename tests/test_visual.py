"""Cobertura de helpers visuais."""
from __future__ import annotations

from kiro_dash.visual import bar_inline, sparkline


def test_bar_inline_zero():
    assert bar_inline(0.0, width=10) == "░" * 10


def test_bar_inline_meio():
    bar = bar_inline(0.5, width=10)
    assert bar.count("█") == 5
    assert bar.count("░") == 5


def test_bar_inline_completo():
    assert bar_inline(1.0, width=10) == "█" * 10


def test_bar_inline_cap_em_1():
    assert bar_inline(2.0, width=10) == "█" * 10


def test_bar_inline_negativo_vira_zero():
    assert bar_inline(-0.5, width=10) == "░" * 10


def test_sparkline_serie_simples():
    out = sparkline([0, 1, 2, 3, 4, 5, 6, 7])
    assert len(out) == 8
    assert out[-1] == "█"
    assert out[0] == "▁"


def test_sparkline_lista_vazia():
    assert sparkline([]) == ""


def test_sparkline_todos_iguais():
    out = sparkline([5, 5, 5, 5])
    assert all(c == "▁" for c in out)


def test_sparkline_cap_em_max_chars():
    out = sparkline([1, 2, 3, 4, 5], max_chars=3)
    assert len(out) == 3
