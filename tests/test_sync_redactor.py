"""Tests T4-W7 — redator de sessões IDE para sync."""
from __future__ import annotations

import json

from kiro_dash.sync_redactor import (
    REDACTED,
    redact_action,
    redact_execution_dict,
    redact_history_item,
    redact_session_dict,
)


def test_redact_history_item_removes_message():
    item = {"message": "secret prompt", "contextItems": [], "other": 1}
    out = redact_history_item(item)
    assert "message" not in out
    assert out["other"] == 1


def test_redact_history_item_removes_editor_state():
    item = {"editorState": {"selection": "x", "value": "secret"}}
    out = redact_history_item(item)
    assert "editorState" not in out


def test_redact_history_item_zeros_context_items_content():
    item = {"contextItems": [{"content": "secret"}, {"content": "more"}]}
    out = redact_history_item(item)
    assert out["contextItems"] == [{"<count>": 2}]


def test_redact_action_removes_raw_input():
    a = {
        "actionId": "x",
        "actionType": "runCommand",
        "rawInput": {"command": "rm -rf /", "explanation": "..."},
    }
    out = redact_action(a)
    assert "rawInput" not in out
    assert out["actionId"] == "x"


def test_redact_action_redacts_input_command():
    a = {
        "actionType": "runCommand",
        "input": {"command": "ls -la /home/user/secrets", "cwd": "/tmp", "terminalId": "t-1"},
    }
    out = redact_action(a)
    assert out["input"]["command"] == REDACTED
    assert out["input"]["cwd"] == "/tmp"
    assert out["input"]["terminalId"] == "t-1"


def test_redact_action_redacts_input_filetext():
    a = {
        "actionType": "create",
        "input": {"path": "/tmp/file.py", "fileText": "import secrets..."},
    }
    out = redact_action(a)
    assert out["input"]["fileText"] == REDACTED
    assert out["input"]["path"] == "/tmp/file.py"


def test_redact_action_redacts_replace_strings():
    a = {
        "actionType": "replace",
        "input": {"path": "/x", "oldStr": "PASSWORD=abc", "newStr": "PASSWORD=xyz"},
    }
    out = redact_action(a)
    assert out["input"]["oldStr"] == REDACTED
    assert out["input"]["newStr"] == REDACTED
    assert out["input"]["path"] == "/x"


def test_redact_action_redacts_output_content():
    a = {
        "actionType": "say",
        "output": {"message": "Aqui está o resultado: secret_value"},
    }
    out = redact_action(a)
    assert out["output"]["message"] == REDACTED


def test_redact_action_redacts_output_command_output():
    a = {
        "actionType": "runCommand",
        "output": {"exitCode": 0, "output": "secret-token-leaked"},
    }
    out = redact_action(a)
    assert out["output"]["output"] == REDACTED
    assert out["output"]["exitCode"] == 0


def test_redact_action_preserves_intent_result():
    a = {
        "actionType": "intentClassification",
        "intentResult": {"classification": "do", "finalIntent": {"type": "do"}},
    }
    out = redact_action(a)
    assert out["intentResult"]["classification"] == "do"


def test_redact_session_dict_redacts_all_history(tmp_path):
    session = {
        "sessionId": "s1",
        "title": "minha sessão",
        "history": [
            {"message": "user secret", "contextItems": [{"content": "x"}]},
            {"message": "assistant secret", "editorState": {"value": "y"}},
        ],
    }
    out = redact_session_dict(session)
    assert out["sessionId"] == "s1"
    assert out["title"] == "minha sessão"  # title preservado
    assert all("message" not in h for h in out["history"])
    assert all("editorState" not in h for h in out["history"])


def test_redact_session_dict_does_not_mutate_original():
    session = {"history": [{"message": "secret"}]}
    original_msg = session["history"][0]["message"]
    _ = redact_session_dict(session)
    assert session["history"][0]["message"] == original_msg


def test_redact_execution_dict_redacts_actions():
    execution = {
        "executionId": "e1",
        "actions": [
            {"actionType": "say", "output": {"message": "secret response"}},
            {
                "actionType": "runCommand",
                "input": {"command": "secret cmd", "cwd": "/x"},
                "rawInput": {"command": "secret"},
                "output": {"output": "secret stdout"},
            },
        ],
    }
    out = redact_execution_dict(execution)
    assert out["actions"][0]["output"]["message"] == REDACTED
    assert out["actions"][1]["input"]["command"] == REDACTED
    assert out["actions"][1]["input"]["cwd"] == "/x"
    assert "rawInput" not in out["actions"][1]
    assert out["actions"][1]["output"]["output"] == REDACTED


def test_redact_execution_dict_redacts_input_data_messages():
    execution = {
        "input": {
            "data": {
                "messages": [
                    {"role": "user", "content": "secret prompt"},
                    {"role": "assistant", "content": "secret response"},
                ],
            },
        },
    }
    out = redact_execution_dict(execution)
    msgs = out["input"]["data"]["messages"]
    assert all(m["content"] == REDACTED for m in msgs)
    assert msgs[0]["role"] == "user"


def test_redact_execution_dict_redacts_context_messages():
    execution = {
        "context": {
            "messages": [{"role": "system", "content": "secret system prompt"}],
        },
    }
    out = redact_execution_dict(execution)
    assert out["context"]["messages"][0]["content"] == REDACTED


def test_redact_execution_dict_preserves_usage_summary():
    execution = {
        "executionId": "e1",
        "usageSummary": [
            {"usage": 0.5, "unit": "credit", "usedTools": ["read_files"]},
        ],
    }
    out = redact_execution_dict(execution)
    assert out["usageSummary"] == execution["usageSummary"]


def test_redact_idempotent():
    """Aplicar redação 2x deve dar o mesmo resultado."""
    execution = {
        "actions": [
            {"actionType": "say", "output": {"message": "secret"}},
        ],
    }
    once = redact_execution_dict(execution)
    twice = redact_execution_dict(once)
    assert json.dumps(once, sort_keys=True) == json.dumps(twice, sort_keys=True)


def test_redact_no_secret_strings_in_output():
    """Sanity-check: o output redatado não pode conter palavras-chave sensíveis."""
    secret_words = ["secret_value", "PASSWORD=abc", "secret-token-leaked"]
    execution = {
        "actions": [
            {"actionType": "say", "output": {"message": "msg with secret_value"}},
            {
                "actionType": "replace",
                "input": {"oldStr": "PASSWORD=abc", "newStr": "PASSWORD=xyz"},
            },
            {
                "actionType": "runCommand",
                "output": {"output": "secret-token-leaked"},
            },
        ],
    }
    out_str = json.dumps(redact_execution_dict(execution))
    for word in secret_words:
        assert word not in out_str, f"Vazou: {word}"
