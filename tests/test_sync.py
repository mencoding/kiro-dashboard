"""Testes do wrapper de sync — sem chamadas reais ao rclone."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

from kiro_dash.sync import (
    SyncConfig,
    rclone_available,
    rclone_remote_exists,
    sync_pull,
    sync_push,
)


def test_rclone_available_when_binary_exists():
    with patch("shutil.which", return_value="/usr/bin/rclone"):
        assert rclone_available() is True


def test_rclone_available_when_binary_missing():
    with patch("shutil.which", return_value=None):
        assert rclone_available() is False


def test_rclone_remote_exists_listremotes_match():
    fake = MagicMock(returncode=0, stdout="gdrive-pessoal:\nother:\n")
    with patch("subprocess.run", return_value=fake):
        assert rclone_remote_exists("gdrive-pessoal") is True


def test_rclone_remote_exists_listremotes_no_match():
    fake = MagicMock(returncode=0, stdout="other:\n")
    with patch("subprocess.run", return_value=fake):
        assert rclone_remote_exists("gdrive-pessoal") is False


def test_sync_push_invokes_rclone_with_correct_filters(tmp_path):
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    (sessions_dir / "abc.json").write_text("{}")
    (sessions_dir / "abc.jsonl").write_text("ignored")
    (sessions_dir / "abc.lock").write_text("ignored")

    cfg = SyncConfig(remote="gdrive-pessoal", remote_path="kiro-dash/sessions")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        sync_push(cfg, sessions_dir)

    args = mock_run.call_args[0][0]
    assert args[0] == "rclone"
    assert "copy" in args
    assert str(sessions_dir) in args
    assert "gdrive-pessoal:kiro-dash/sessions" in args
    # Filtros essenciais: inclui .json, exclui .jsonl/.lock e subdirs
    full_cmd = " ".join(args)
    assert "--include=*.json" in full_cmd
    assert "--exclude=*.jsonl" in full_cmd
    assert "--exclude=*.lock" in full_cmd
    assert "--exclude=*/" in full_cmd  # sub-diretórios (tasks/) ignorados


def test_sync_pull_invokes_rclone_correctly(tmp_path):
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    cfg = SyncConfig(remote="gdrive-pessoal", remote_path="kiro-dash/sessions")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        sync_pull(cfg, sessions_dir)

    args = mock_run.call_args[0][0]
    assert args[0] == "rclone"
    assert "copy" in args
    # Ordem inversa do push: remote -> local
    src_idx = args.index("copy") + 1
    assert args[src_idx] == "gdrive-pessoal:kiro-dash/sessions"
    assert args[src_idx + 1] == str(sessions_dir)


def test_sync_push_returns_false_on_rclone_failure(tmp_path):
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    cfg = SyncConfig(remote="gdrive-pessoal", remote_path="kiro-dash/sessions")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="auth error")
        ok, err = sync_push(cfg, sessions_dir)
    assert ok is False
    assert "auth error" in err
