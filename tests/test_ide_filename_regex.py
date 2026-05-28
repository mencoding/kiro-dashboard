"""Tests T1-W9 — _EXECUTION_ID_RE aceita UUID-com-hífens E 32-hex.

Wave 9 (v0.7.3): O Kiro IDE mudou o formato do nome dos arquivos de
execution blob de UUID para storage-key opaca de 32 hex chars sem
hífens. O conteúdo do JSON dentro do blob ainda usa executionId em
UUID format. A regex de pré-filtro precisa aceitar ambos formatos
para suportar instalações novas (hex32) e antigas (UUID).

Ver ADR-0002 para rationale.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from kiro_dash.backends.ide_sessions import (
    _EXECUTION_ID_RE,
    IdeSessionBackend,
    read_execution,
)


# ── Regex direto ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "filename",
    [
        # UUID com hífens (formato antigo)
        "8e2c534f-0296-4bc8-9048-196ca3521378",
        "98293fbd-f204-418e-9c87-d60143bc293c",
        # 32 hex chars sem hífens (formato atual, storage-key opaca)
        "56e3a12eb62ae614d6506852be100670",
        "5616bf4186bbe2966bae04376f71b0be",
        "977fe086f1f28f04fe9cd002242f6768",
        "f8295071aaff5ece84bd3e7bb525cb09",
    ],
)
def test_regex_accepts_valid_execution_filenames(filename):
    """Aceita ambos os formatos de filename observados em produção."""
    assert _EXECUTION_ID_RE.match(filename) is not None


@pytest.mark.parametrize(
    "filename",
    [
        # Auxiliares que devem continuar rejeitados
        "config.json",
        "profile.json",
        "sessions.json",
        # Comprimentos errados
        "short",
        "abc123",
        "a" * 31,
        "a" * 33,
        # Chars inválidos
        "8e2c534f-0296-4bc8-9048-196ca352137G",  # 'G' não é hex
        "/home/user/foo",
        # Vazio
        "",
    ],
)
def test_regex_rejects_invalid_filenames(filename):
    """Rejeita filenames que não são UUID nem hex32."""
    assert _EXECUTION_ID_RE.match(filename) is None


# Nota: ``f62de366d0006e17ea00a01f6624aabf`` (catalog index) é
# tecnicamente hex32 válido — a regex aceita por design. A
# discriminação dele não vem da regex; vem de
# ``iter_profile_hash_dirs`` que já o trata como arquivo (não-dir)
# no parent level. Ele NUNCA entra no path do
# ``inner_dir.iterdir()`` onde a regex é aplicada.


# ── Integration: backend lê executions com nome hex32 ────────────────


def _write_execution_blob(path: Path, exec_id: str, chat_session_id: str, credits: float = 0.5) -> None:
    """Cria um blob de execution válido."""
    blob = {
        "executionId": exec_id,
        "workflowType": "chat-agent",
        "status": "succeed",
        "startTime": 1779915457381,
        "endTime": 1779915625116,
        "chatSessionId": chat_session_id,
        "title": "Test execution",
        "autonomyMode": "supervised",
        "actions": [],
        "context": {},
        "result": {},
        "input": {"data": {}},
        "usageSummary": [
            {"usedTools": ["read_file"], "usage": credits, "unit": "credit", "unitPlural": "credits"}
        ],
        "contextUsagePercentage": 0.5,
    }
    path.write_text(json.dumps(blob))


def test_scan_finds_executions_with_hex32_filename(tmp_path, monkeypatch):
    """Backend lê executions cujos arquivos têm nome em hex32 (formato atual)."""
    # Layout completo mínimo
    root = tmp_path / "kiro.kiroagent"
    account = root / "52425d8aadfb99e2008e148772003fb6"
    inner = account / "414d1636299d2b9e4ce7e17fb11f63e9"
    inner.mkdir(parents=True)
    # Catalog file no nível account
    (account / "f62de366d0006e17ea00a01f6624aabf").write_text(
        json.dumps({"version": 1, "executions": []})
    )
    # workspace-sessions com 1 sessão
    ws = root / "workspace-sessions" / "L2hvbWUvbWVuemFuaQ__"
    ws.mkdir(parents=True)
    (ws / "sessions.json").write_text(
        json.dumps([{
            "sessionId": "8e2c534f-0296-4bc8-9048-196ca3521378",
            "title": "Test",
            "dateCreated": "1779909979236",
            "workspaceDirectory": "/home/menzani"
        }])
    )
    (ws / "8e2c534f-0296-4bc8-9048-196ca3521378.json").write_text(
        json.dumps({
            "sessionId": "8e2c534f-0296-4bc8-9048-196ca3521378",
            "dateCreated": 1779909979236,
            "history": [],
            "type": "ChatSession",
            "autonomyMode": "supervised",
            "selectedModel": "kiro:auto",
            "title": "Test"
        })
    )
    # Execution blobs com filename hex32 (formato novo)
    _write_execution_blob(
        inner / "56e3a12eb62ae614d6506852be100670",
        "exec1-7d5a-4a4a-9c87-d60143bc293c",
        "8e2c534f-0296-4bc8-9048-196ca3521378",
        credits=1.5,
    )
    _write_execution_blob(
        inner / "977fe086f1f28f04fe9cd002242f6768",
        "exec2-7d5a-4a4a-9c87-d60143bc293c",
        "8e2c534f-0296-4bc8-9048-196ca3521378",
        credits=2.0,
    )

    monkeypatch.delenv("KIRO_DASH_NO_IDE_SESSIONS", raising=False)
    backend = IdeSessionBackend(root=root)
    sessions = backend.list_sessions()
    assert len(sessions) == 1
    s = sessions[0]
    assert len(s.turns) == 2
    total = sum(t.credits for t in s.turns)
    assert total == pytest.approx(3.5)


def test_scan_finds_executions_with_uuid_filename(tmp_path, monkeypatch):
    """Backend ainda lê executions com nome em UUID (formato antigo)."""
    root = tmp_path / "kiro.kiroagent"
    account = root / "52425d8aadfb99e2008e148772003fb6"
    inner = account / "414d1636299d2b9e4ce7e17fb11f63e9"
    inner.mkdir(parents=True)
    (account / "f62de366d0006e17ea00a01f6624aabf").write_text(
        json.dumps({"version": 1, "executions": []})
    )
    ws = root / "workspace-sessions" / "L2hvbWUvbWVuemFuaQ__"
    ws.mkdir(parents=True)
    (ws / "sessions.json").write_text(
        json.dumps([{
            "sessionId": "ABCDEF12-0296-4bc8-9048-196ca3521378".lower(),
            "title": "Old",
            "dateCreated": "1700000000000",
            "workspaceDirectory": "/home/old"
        }])
    )
    (ws / "abcdef12-0296-4bc8-9048-196ca3521378.json").write_text(
        json.dumps({"sessionId": "abcdef12-0296-4bc8-9048-196ca3521378",
                    "dateCreated": 1700000000000,
                    "history": [], "type": "ChatSession", "autonomyMode": "supervised",
                    "selectedModel": "kiro:auto", "title": "Old"})
    )
    # Filename em UUID format
    _write_execution_blob(
        inner / "98293fbd-f204-418e-9c87-d60143bc293c",
        "98293fbd-f204-418e-9c87-d60143bc293c",
        "abcdef12-0296-4bc8-9048-196ca3521378",
        credits=4.0,
    )

    monkeypatch.delenv("KIRO_DASH_NO_IDE_SESSIONS", raising=False)
    backend = IdeSessionBackend(root=root)
    sessions = backend.list_sessions()
    assert len(sessions) == 1
    assert len(sessions[0].turns) == 1
    assert sessions[0].turns[0].credits == pytest.approx(4.0)


def test_scan_ignores_non_matching_filenames(tmp_path, monkeypatch):
    """Backend ignora arquivos auxiliares dentro de inner_dir."""
    root = tmp_path / "kiro.kiroagent"
    account = root / "52425d8aadfb99e2008e148772003fb6"
    inner = account / "414d1636299d2b9e4ce7e17fb11f63e9"
    inner.mkdir(parents=True)
    (account / "f62de366d0006e17ea00a01f6624aabf").write_text(
        json.dumps({"version": 1, "executions": []})
    )
    ws = root / "workspace-sessions" / "L2hvbWUvbWVuemFuaQ__"
    ws.mkdir(parents=True)
    (ws / "sessions.json").write_text(
        json.dumps([{
            "sessionId": "8e2c534f-0296-4bc8-9048-196ca3521378",
            "title": "T",
            "dateCreated": "1779909979236",
            "workspaceDirectory": "/x"
        }])
    )
    (ws / "8e2c534f-0296-4bc8-9048-196ca3521378.json").write_text(
        json.dumps({"sessionId": "8e2c534f-0296-4bc8-9048-196ca3521378",
                    "dateCreated": 1779909979236,
                    "history": [], "type": "ChatSession", "autonomyMode": "supervised",
                    "selectedModel": "kiro:auto", "title": "T"})
    )
    # Arquivos que NÃO devem ser lidos
    (inner / "config.json").write_text("{}")
    (inner / "metadata").write_text("not json")
    (inner / "junk-too-short").write_text("{}")
    # Arquivo válido para confirmar que outras leituras funcionam
    _write_execution_blob(
        inner / "56e3a12eb62ae614d6506852be100670",
        "real-exec-id-7d5a-4a4a-9c87-d60143bc293c",
        "8e2c534f-0296-4bc8-9048-196ca3521378",
        credits=1.0,
    )

    monkeypatch.delenv("KIRO_DASH_NO_IDE_SESSIONS", raising=False)
    backend = IdeSessionBackend(root=root)
    sessions = backend.list_sessions()
    assert len(sessions) == 1
    assert len(sessions[0].turns) == 1  # só o blob válido


# ── Read_execution defensive: arquivo lixo passa regex mas read falha ─


def test_read_execution_returns_none_on_invalid_json(tmp_path):
    """Mesmo se um arquivo passar o filtro de regex (32 hex), ele só vira
    Turn se read_execution conseguir parsear corretamente. Defesa em
    profundidade: regex pré-filtra I/O, mas read_execution decide schema.
    """
    bad = tmp_path / "56e3a12eb62ae614d6506852be100670"
    bad.write_text("not valid json {{{")
    assert read_execution(bad) is None
