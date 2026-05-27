"""Tests T4-W7 — sync de sessões IDE com redação."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from kiro_dash.sync import (
    SyncConfig,
    _redact_and_stage_ide_sessions,
    sync_push_ide,
)
from tests.fixtures.ide.build_ide_layout import (
    DEFAULT_WORKSPACE_PATH,
    SESSION_ID,
    build_ide_layout,
)


def test_stage_redacts_session_files(tmp_path):
    """Sessions individuais são redatadas (history.message removido)."""
    ide_root = build_ide_layout(tmp_path / "ide")
    stage = tmp_path / "stage"
    stage.mkdir()
    count = _redact_and_stage_ide_sessions(ide_root, stage)
    assert count >= 1
    # Encontrar a sessão staged
    from kiro_dash.backends.workspace_codec import encode

    ws_b64 = encode(DEFAULT_WORKSPACE_PATH)
    sess_staged = stage / ws_b64 / f"{SESSION_ID}.json"
    assert sess_staged.is_file()
    payload = json.loads(sess_staged.read_text())
    # history não deve ter campo message preservado
    for h in payload.get("history", []):
        assert "message" not in h, "history.message não foi redatado"
        assert "editorState" not in h, "editorState não foi redatado"


def test_stage_preserves_sessions_json_catalog(tmp_path):
    """Catálogo sessions.json (só metadata) passa inalterado."""
    ide_root = build_ide_layout(tmp_path / "ide")
    stage = tmp_path / "stage"
    stage.mkdir()
    _redact_and_stage_ide_sessions(ide_root, stage)
    from kiro_dash.backends.workspace_codec import encode

    ws_b64 = encode(DEFAULT_WORKSPACE_PATH)
    catalog_staged = stage / ws_b64 / "sessions.json"
    assert catalog_staged.is_file()
    payload = json.loads(catalog_staged.read_text())
    assert isinstance(payload, list)
    assert payload[0]["sessionId"] == SESSION_ID


def test_stage_returns_zero_when_no_workspace_sessions(tmp_path):
    """Diretório sem workspace-sessions/ retorna 0."""
    empty_ide = tmp_path / "ide-empty"
    empty_ide.mkdir()
    stage = tmp_path / "stage"
    stage.mkdir()
    count = _redact_and_stage_ide_sessions(empty_ide, stage)
    assert count == 0


def test_sync_push_ide_ok_when_empty(tmp_path):
    """IDE root vazio → sucesso sem chamar rclone."""
    empty_ide = tmp_path / "ide-empty"
    empty_ide.mkdir()
    (empty_ide / "workspace-sessions").mkdir()
    cfg = SyncConfig(remote="testremote", remote_path="kdash")
    with patch("kiro_dash.sync._run_rclone") as run:
        ok, err = sync_push_ide(cfg, empty_ide)
    assert ok is True
    assert err == ""
    run.assert_not_called()  # nenhum push porque count=0


def test_sync_push_ide_fails_when_root_missing(tmp_path):
    cfg = SyncConfig(remote="testremote", remote_path="kdash")
    ok, err = sync_push_ide(cfg, tmp_path / "no_such_dir")
    assert ok is False
    assert "não é diretório" in err


def test_sync_push_ide_calls_rclone_with_redacted_dir(tmp_path):
    """Com fixture real, sync_push_ide redata e chama rclone copy."""
    ide_root = build_ide_layout(tmp_path / "ide")
    cfg = SyncConfig(remote="testremote", remote_path="kdash")

    captured_args = []

    def fake_run(args):
        captured_args.append(args)
        return True, ""

    with patch("kiro_dash.sync._run_rclone", side_effect=fake_run):
        ok, err = sync_push_ide(cfg, ide_root)

    assert ok is True
    assert err == ""
    assert len(captured_args) == 1
    cmd = captured_args[0]
    assert cmd[0] == "rclone"
    assert cmd[1] == "copy"
    # Source deve ser um path temporário (não o ide_root original)
    assert str(ide_root) not in cmd[2]  # NÃO é o caminho real
    # Destination tem ide-sessions/ subpath
    assert "ide-sessions" in cmd[3]


def test_sync_push_ide_redacted_content_does_not_leak(tmp_path):
    """End-to-end: capturar arquivos staged e verificar zero leakage."""
    ide_root = build_ide_layout(tmp_path / "ide")
    cfg = SyncConfig(remote="testremote", remote_path="kdash")

    # Capturar staged files antes do tmpdir ser removido
    captured_files: list[tuple[Path, dict]] = []

    def fake_run(args):
        # args[2] é o source (stage dir)
        stage = Path(args[2])
        for jf in stage.rglob("*.json"):
            payload = json.loads(jf.read_text())
            captured_files.append((jf, payload))
        return True, ""

    with patch("kiro_dash.sync._run_rclone", side_effect=fake_run):
        sync_push_ide(cfg, ide_root)

    # Sanity-check: capturamos algo
    assert captured_files, "nenhum arquivo capturado"

    # Verificar que sessões individuais NÃO têm message preservada
    for path, payload in captured_files:
        if path.name == "sessions.json":
            continue  # catálogo passa inalterado
        for h in payload.get("history", []):
            assert "message" not in h
            assert "editorState" not in h
        for action in payload.get("actions", []):
            # rawInput sempre removido
            assert "rawInput" not in action
