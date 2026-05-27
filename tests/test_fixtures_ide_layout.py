"""Tests do builder de fixtures IDE (T1)."""
from __future__ import annotations

import json

from kiro_dash.backends.workspace_codec import encode
from tests.fixtures.ide.build_ide_layout import (
    CATALOG_FILENAME,
    DEFAULT_PROFILE_HASH,
    DEFAULT_WORKSPACE_PATH,
    EXEC_CHAT,
    EXEC_DO_COMPLEX,
    EXEC_DO_SIMPLE,
    EXEC_DO_WRITE,
    EXEC_RUNNING,
    EXEC_SPEC_DISPATCH,
    EXEC_SPEC_GENERATION,
    INNER_HASH,
    SESSION_ID,
    build_ide_layout,
)


def test_layout_skeleton_created(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    assert kiro_root.is_dir()
    assert kiro_root.name == "kiro.kiroagent"
    assert (kiro_root / "config.json").is_file()
    assert (kiro_root / "profile.json").is_file()
    assert (kiro_root / "default" / CATALOG_FILENAME).is_file()
    assert (kiro_root / DEFAULT_PROFILE_HASH).is_dir()
    assert (kiro_root / DEFAULT_PROFILE_HASH / CATALOG_FILENAME).is_file()
    assert (kiro_root / DEFAULT_PROFILE_HASH / INNER_HASH).is_dir()
    assert (kiro_root / "workspace-sessions").is_dir()


def test_workspace_dir_uses_base64url_encoded_name(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    expected_b64 = encode(DEFAULT_WORKSPACE_PATH)
    ws_dir = kiro_root / "workspace-sessions" / expected_b64
    assert ws_dir.is_dir()
    assert (ws_dir / "sessions.json").is_file()
    assert (ws_dir / f"{SESSION_ID}.json").is_file()


def test_session_json_shape(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    ws_b64 = encode(DEFAULT_WORKSPACE_PATH)
    sess_path = kiro_root / "workspace-sessions" / ws_b64 / f"{SESSION_ID}.json"
    sess = json.loads(sess_path.read_text())
    assert sess["sessionId"] == SESSION_ID
    assert sess["workspaceDirectory"] == DEFAULT_WORKSPACE_PATH
    assert sess["sessionType"] == "vibe"
    assert sess["autonomyMode"] == "Autopilot"
    assert sess["selectedModel"] == "auto"
    assert "history" in sess
    assert "contextUsagePercentage" in sess


def test_executions_catalog_has_seven_entries_with_running(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    cat_path = kiro_root / DEFAULT_PROFILE_HASH / CATALOG_FILENAME
    cat = json.loads(cat_path.read_text())
    assert len(cat["executions"]) == 7
    statuses = {e["status"] for e in cat["executions"]}
    assert statuses == {"succeed", "running"}
    types = {e["type"] for e in cat["executions"]}
    assert types == {"chat-agent", "spec-generation"}


def test_executions_catalog_no_running_when_excluded(tmp_path):
    kiro_root = build_ide_layout(tmp_path, include_running=False)
    cat = json.loads((kiro_root / DEFAULT_PROFILE_HASH / CATALOG_FILENAME).read_text())
    assert len(cat["executions"]) == 6
    assert all(e["status"] == "succeed" for e in cat["executions"])
    inner = kiro_root / DEFAULT_PROFILE_HASH / INNER_HASH
    assert not (inner / EXEC_RUNNING).exists()


def test_all_seven_execution_files_exist(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    inner = kiro_root / DEFAULT_PROFILE_HASH / INNER_HASH
    for exec_id in [
        EXEC_CHAT,
        EXEC_DO_SIMPLE,
        EXEC_DO_COMPLEX,
        EXEC_DO_WRITE,
        EXEC_SPEC_DISPATCH,
        EXEC_SPEC_GENERATION,
        EXEC_RUNNING,
    ]:
        path = inner / exec_id
        assert path.is_file()
        payload = json.loads(path.read_text())
        assert payload["executionId"] == exec_id


def test_chat_execution_shape(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    inner = kiro_root / DEFAULT_PROFILE_HASH / INNER_HASH
    chat = json.loads((inner / EXEC_CHAT).read_text())
    assert chat["workflowType"] == "chat-agent"
    assert chat["status"] == "succeed"
    assert chat["chatSessionId"] == SESSION_ID
    action_types = [a["actionType"] for a in chat["actions"]]
    assert "intentClassification" in action_types
    intent = next(a for a in chat["actions"] if a["actionType"] == "intentClassification")
    assert intent["intentResult"]["classification"] == "chat"


def test_do_simple_has_execute_bash_in_usage_summary(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    inner = kiro_root / DEFAULT_PROFILE_HASH / INNER_HASH
    do_s = json.loads((inner / EXEC_DO_SIMPLE).read_text())
    intent = next(a for a in do_s["actions"] if a["actionType"] == "intentClassification")
    assert intent["intentResult"]["classification"] == "do"
    used_tools = set()
    for u in do_s["usageSummary"]:
        used_tools.update(u.get("usedTools", []))
    assert "execute_bash" in used_tools


def test_do_complex_has_full_process_lifecycle(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    inner = kiro_root / DEFAULT_PROFILE_HASH / INNER_HASH
    do_c = json.loads((inner / EXEC_DO_COMPLEX).read_text())
    used_tools = set()
    for u in do_c["usageSummary"]:
        used_tools.update(u.get("usedTools", []))
    assert {"read_files", "execute_bash", "control_bash_process", "get_process_output"} <= used_tools


def test_do_write_has_fs_write_and_replace(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    inner = kiro_root / DEFAULT_PROFILE_HASH / INNER_HASH
    do_w = json.loads((inner / EXEC_DO_WRITE).read_text())
    used_tools = set()
    for u in do_w["usageSummary"]:
        used_tools.update(u.get("usedTools", []))
    assert "fs_write" in used_tools
    assert "str_replace" in used_tools
    assert "getDiagnostics" in used_tools


def test_spec_dispatch_has_intent_spec_and_specagent_action(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    inner = kiro_root / DEFAULT_PROFILE_HASH / INNER_HASH
    sd = json.loads((inner / EXEC_SPEC_DISPATCH).read_text())
    intent = next(a for a in sd["actions"] if a["actionType"] == "intentClassification")
    assert intent["intentResult"]["classification"] == "spec"
    action_types = [a["actionType"] for a in sd["actions"]]
    assert "specAgent" in action_types
    assert "userInput" in action_types


def test_spec_generation_has_no_intent_classification(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    inner = kiro_root / DEFAULT_PROFILE_HASH / INNER_HASH
    sg = json.loads((inner / EXEC_SPEC_GENERATION).read_text())
    assert sg["workflowType"] == "spec-generation"
    action_types = [a["actionType"] for a in sg["actions"]]
    assert "intentClassification" not in action_types
    assert "invokeSubAgent" in action_types
    assert "subagent_response" in action_types


def test_running_execution_has_status_running_and_endtime_zero(tmp_path):
    kiro_root = build_ide_layout(tmp_path)
    inner = kiro_root / DEFAULT_PROFILE_HASH / INNER_HASH
    run = json.loads((inner / EXEC_RUNNING).read_text())
    assert run["status"] == "running"
    assert run["endTime"] == 0
    assert run["workflowType"] == "spec-generation"


def test_redaction_no_secret_strings(tmp_path):
    """Sanity: nenhuma fixture deve conter strings que pareçam conteúdo real."""
    kiro_root = build_ide_layout(tmp_path)
    forbidden = ["menzani", "/home/menzani", "kiro.dev", "@gmail", "ya29", "1//"]
    for f in kiro_root.rglob("*"):
        if f.is_file():
            content = f.read_text(errors="ignore")
            for pat in forbidden:
                assert pat not in content, f"Padrão sensível {pat!r} em {f}"


def test_extra_workspaces_creates_extra_dirs(tmp_path):
    extra = ["/home/test/another", "/srv/work/xyz"]
    kiro_root = build_ide_layout(tmp_path, extra_workspaces=extra)
    ws_root = kiro_root / "workspace-sessions"
    assert (ws_root / encode(DEFAULT_WORKSPACE_PATH)).is_dir()
    for wp in extra:
        assert (ws_root / encode(wp)).is_dir()


def test_extra_profile_hashes_creates_extra_dirs(tmp_path):
    extra = ["1111111111111111111111111111111b", "2222222222222222222222222222222c"]
    kiro_root = build_ide_layout(tmp_path, extra_profile_hashes=extra)
    assert (kiro_root / DEFAULT_PROFILE_HASH / CATALOG_FILENAME).is_file()
    for ph in extra:
        assert (kiro_root / ph / CATALOG_FILENAME).is_file()
        assert (kiro_root / ph / INNER_HASH).is_dir()
