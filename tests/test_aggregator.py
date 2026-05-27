"""Testes do agregador — funções de janela temporal."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from kiro_dash.aggregator import turns_in_last_days
from tests.fixtures.sessions_synthetic import make_session, make_turn


def test_turns_in_last_days_filters_by_window():
    now = datetime.now(timezone.utc)
    s = make_session(
        turns=[
            make_turn(end_timestamp=now - timedelta(days=10), credits=1.0),
            make_turn(end_timestamp=now - timedelta(days=3), credits=2.0),
            make_turn(end_timestamp=now - timedelta(hours=1), credits=4.0),
        ]
    )

    pairs = turns_in_last_days([s], days=7)
    credits = sorted(t.credits for _, t in pairs)
    assert credits == [2.0, 4.0]


def test_turns_in_last_days_empty_when_no_match():
    now = datetime.now(timezone.utc)
    s = make_session(turns=[make_turn(end_timestamp=now - timedelta(days=30))])
    assert turns_in_last_days([s], days=7) == []


def test_turns_in_last_days_zero_days_returns_empty():
    now = datetime.now(timezone.utc)
    s = make_session(turns=[make_turn(end_timestamp=now)])
    assert turns_in_last_days([s], days=0) == []


from kiro_dash.aggregator import aggregate_tools_in_window


def test_aggregate_tools_in_window_groups_by_name(tmp_path):
    s1 = tmp_path / "11111111.jsonl"
    s2 = tmp_path / "22222222.jsonl"
    s1.write_text(
        '{"version":"v1","kind":"AssistantMessage","data":{"content":['
        '{"kind":"toolUse","data":{"name":"read","toolUseId":"a"}},'
        '{"kind":"toolUse","data":{"name":"shell","toolUseId":"b"}}'
        ']}}\n'
    )
    s2.write_text(
        '{"version":"v1","kind":"AssistantMessage","data":{"content":['
        '{"kind":"toolUse","data":{"name":"read","toolUseId":"c"}}'
        ']}}\n'
    )

    aggs = aggregate_tools_in_window(tmp_path, hours=24)
    by_name = {a["name"]: a for a in aggs}
    assert by_name["read"]["count"] == 2
    assert by_name["shell"]["count"] == 1
    assert by_name["read"]["sessions"] == 2
    assert by_name["shell"]["sessions"] == 1


def test_aggregate_tools_in_window_excludes_old_files(tmp_path):
    import os
    import time

    old = tmp_path / "old.jsonl"
    old.write_text(
        '{"version":"v1","kind":"AssistantMessage","data":{"content":['
        '{"kind":"toolUse","data":{"name":"read","toolUseId":"x"}}]}}\n'
    )
    past = time.time() - 48 * 3600
    os.utime(old, (past, past))

    aggs = aggregate_tools_in_window(tmp_path, hours=24)
    assert aggs == []


from pathlib import Path
from unittest.mock import patch

from kiro_dash.aggregator import aggregate_by_project


def test_aggregate_by_project_consolida_subpastas_em_um_label(tmp_path):
    """Sessões em subpastas do mesmo projeto consolidam num único label."""
    with patch.object(Path, "home", return_value=tmp_path):
        s1 = make_session(
            session_id="aaaa",
            cwd=str(tmp_path / "iris/projetos/institucional/auto-normas"),
            turns=[make_turn(end_timestamp=datetime.now(timezone.utc), credits=1.0)],
        )
        s2 = make_session(
            session_id="bbbb",
            cwd=str(tmp_path / "iris/projetos/institucional/auto-normas/workspace"),
            turns=[make_turn(end_timestamp=datetime.now(timezone.utc), credits=2.0)],
        )
        s3 = make_session(
            session_id="cccc",
            cwd=str(tmp_path / "iris/projetos/pessoal/docente-ifsp"),
            turns=[make_turn(end_timestamp=datetime.now(timezone.utc), credits=4.0)],
        )

        pairs = [
            (s, t)
            for s in (s1, s2, s3)
            for t in s.turns
        ]

        aggs = aggregate_by_project(pairs)

    by_label = {a.label: a for a in aggs}
    assert "institucional/auto-normas" in by_label
    assert by_label["institucional/auto-normas"].credits == 3.0
    assert by_label["institucional/auto-normas"].sessions == 2
    assert by_label["pessoal/docente-ifsp"].credits == 4.0


from kiro_dash.aggregator import filter_by_agent


def test_filter_by_agent_isola_uma():
    now = datetime.now(timezone.utc)
    s_nyx = make_session(agent_name="nyx", turns=[make_turn(end_timestamp=now, credits=10)])
    s_other = make_session(session_id="x", agent_name="kiro_default", turns=[make_turn(end_timestamp=now, credits=5)])
    pairs = [(s, t) for s in (s_nyx, s_other) for t in s.turns]
    out = filter_by_agent(pairs, "nyx")
    assert len(out) == 1
    assert out[0][0].agent_name == "nyx"


def test_filter_by_agent_sem_match_devolve_vazio():
    now = datetime.now(timezone.utc)
    s = make_session(agent_name="nyx", turns=[make_turn(end_timestamp=now)])
    pairs = [(s, t) for t in s.turns]
    out = filter_by_agent(pairs, "inexistente")
    assert out == []


def test_filter_by_agent_none_passa_tudo():
    now = datetime.now(timezone.utc)
    s = make_session(agent_name="nyx", turns=[make_turn(end_timestamp=now)])
    pairs = [(s, t) for t in s.turns]
    out = filter_by_agent(pairs, None)
    assert out == pairs


# ─── aggregate_by_agent_pair (Wave 3 hotfix v0.4.1) ────────────────────────


def test_turns_in_local_day_aceita_now_injetado():
    """Com `now` fixo, comportamento é totalmente determinístico."""
    from kiro_dash.aggregator import turns_in_local_day

    fake_now = datetime(2026, 5, 16, 15, 0, tzinfo=timezone.utc)
    # 15:00 UTC - 8h = 07:00 UTC — still same local day
    s = make_session(turns=[make_turn(end_timestamp=fake_now - timedelta(hours=8), credits=5)])

    pairs = turns_in_local_day([s], now=fake_now)
    assert len(pairs) == 1
    assert pairs[0][1].credits == 5


def test_turns_in_local_day_now_injetado_filtra_dia_anterior():
    """Turn de antes da meia-noite local NÃO entra em today."""
    from kiro_dash.aggregator import turns_in_local_day

    fake_now = datetime(2026, 5, 16, 15, 0, tzinfo=timezone.utc)
    old = fake_now - timedelta(hours=37)
    s = make_session(turns=[make_turn(end_timestamp=old, credits=99)])

    pairs = turns_in_local_day([s], now=fake_now)
    assert pairs == []


def test_turns_in_last_days_now_injetado():
    fake_now = datetime(2026, 5, 16, 15, 0, tzinfo=timezone.utc)
    s = make_session(turns=[
        make_turn(end_timestamp=fake_now - timedelta(days=3), credits=10),
        make_turn(end_timestamp=fake_now - timedelta(days=10), credits=20),
    ])
    pairs = turns_in_last_days([s], days=7, now=fake_now)
    assert len(pairs) == 1
    assert pairs[0][1].credits == 10


def test_turns_in_cycle_now_injetado():
    from kiro_dash.aggregator import turns_in_cycle
    from datetime import date

    fake_now = datetime(2026, 5, 16, 15, 0, tzinfo=timezone.utc)
    cycle = date(2026, 5, 1)
    s = make_session(turns=[
        make_turn(end_timestamp=fake_now - timedelta(days=2), credits=5),
        make_turn(end_timestamp=fake_now - timedelta(days=20), credits=99),
    ])
    pairs = turns_in_cycle([s], cycle, now=fake_now)
    assert sum(t.credits for _, t in pairs) == 5


# ─── aggregate_by_agent_pair (Wave 3 hotfix v0.4.1) ────────────────────────


def test_aggregate_by_agent_pair_separa_runtime_e_persona():
    """Sessão Nyx (persona) cujos turns rodam em kiro_default (runtime) → 1 entrada."""
    from kiro_dash.aggregator import aggregate_by_agent_pair

    now = datetime.now(timezone.utc)
    s_nyx = make_session(
        session_id="nyx",
        agent_name="nyx",
        turns=[
            make_turn(end_timestamp=now, agent_name="kiro_default", credits=10),
            make_turn(end_timestamp=now, agent_name="kiro_default", credits=5),
        ],
    )
    pairs = [(s_nyx, t) for t in s_nyx.turns]

    aggs = aggregate_by_agent_pair(pairs)
    assert len(aggs) == 1
    a = aggs[0]
    assert a.runtime == "kiro_default"
    assert a.persona == "nyx"
    assert a.credits == 15
    assert a.turns == 2
    assert a.sessions == 1


def test_aggregate_by_agent_pair_separa_subagent_auto():
    """Sessão Nyx com mistura kiro_default + auto (subagent) → 2 entradas."""
    from kiro_dash.aggregator import aggregate_by_agent_pair

    now = datetime.now(timezone.utc)
    s = make_session(
        session_id="x",
        agent_name="nyx",
        turns=[
            make_turn(end_timestamp=now, agent_name="kiro_default", credits=10),
            make_turn(end_timestamp=now, agent_name="auto", credits=3),
        ],
    )
    pairs = [(s, t) for t in s.turns]

    aggs = aggregate_by_agent_pair(pairs)
    by_runtime = {a.runtime: a for a in aggs}
    assert set(by_runtime.keys()) == {"kiro_default", "auto"}
    assert by_runtime["kiro_default"].persona == "nyx"
    assert by_runtime["auto"].persona == "nyx"
    assert by_runtime["kiro_default"].credits == 10
    assert by_runtime["auto"].credits == 3


def test_aggregate_by_agent_pair_ordenado_por_creditos_desc():
    from kiro_dash.aggregator import aggregate_by_agent_pair

    now = datetime.now(timezone.utc)
    s1 = make_session(session_id="a", agent_name="nyx",
                      turns=[make_turn(end_timestamp=now, agent_name="kiro_default", credits=2)])
    s2 = make_session(session_id="b", agent_name="iris",
                      turns=[make_turn(end_timestamp=now, agent_name="kiro_default", credits=20)])
    pairs = [(s, t) for s in (s1, s2) for t in s.turns]

    aggs = aggregate_by_agent_pair(pairs)
    assert aggs[0].persona == "iris"
    assert aggs[1].persona == "nyx"


def test_aggregate_by_agent_pair_persona_vazia_vira_interrogacao():
    from kiro_dash.aggregator import aggregate_by_agent_pair

    now = datetime.now(timezone.utc)
    s = make_session(session_id="x", agent_name="",
                     turns=[make_turn(end_timestamp=now, agent_name="", credits=1)])
    pairs = [(s, t) for t in s.turns]

    aggs = aggregate_by_agent_pair(pairs)
    assert aggs[0].runtime == "?"
    assert aggs[0].persona == "?"
