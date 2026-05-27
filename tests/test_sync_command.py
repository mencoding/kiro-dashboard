"""Smoke do subcomando sync."""
from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from kiro_dash.cli import main


def test_sync_push_aborts_when_rclone_missing():
    with patch("kiro_dash.cli.rclone_available", return_value=False):
        runner = CliRunner()
        result = runner.invoke(main, ["sync", "push"])
    assert result.exit_code == 1
    assert "rclone" in result.output.lower()


def test_sync_push_aborts_when_remote_missing():
    with patch("kiro_dash.cli.rclone_available", return_value=True), \
         patch("kiro_dash.cli.rclone_remote_exists", return_value=False):
        runner = CliRunner()
        result = runner.invoke(main, ["sync", "push"])
    assert result.exit_code == 1
    assert "remote" in result.output.lower() or "configurado" in result.output.lower()


def test_sync_push_calls_sync_push_when_environment_ok():
    with patch("kiro_dash.cli.rclone_available", return_value=True), \
         patch("kiro_dash.cli.rclone_remote_exists", return_value=True), \
         patch("kiro_dash.cli.sync_push", return_value=(True, "")) as mock_push:
        runner = CliRunner()
        result = runner.invoke(main, ["sync", "push"])
    assert result.exit_code == 0
    mock_push.assert_called_once()


def test_sync_pull_calls_sync_pull():
    with patch("kiro_dash.cli.rclone_available", return_value=True), \
         patch("kiro_dash.cli.rclone_remote_exists", return_value=True), \
         patch("kiro_dash.cli.sync_pull", return_value=(True, "")) as mock_pull:
        runner = CliRunner()
        result = runner.invoke(main, ["sync", "pull"])
    assert result.exit_code == 0
    mock_pull.assert_called_once()


def test_sync_propagates_failure_message():
    with patch("kiro_dash.cli.rclone_available", return_value=True), \
         patch("kiro_dash.cli.rclone_remote_exists", return_value=True), \
         patch("kiro_dash.cli.sync_push", return_value=(False, "permission denied")):
        runner = CliRunner()
        result = runner.invoke(main, ["sync", "push"])
    assert result.exit_code == 1
    assert "permission denied" in result.output
