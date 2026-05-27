"""Builder de layout completo do Kiro IDE redatado em ``tmp_path``.

Reproduz a árvore de filesystem observada em
``~/.config/Kiro/User/globalStorage/kiro.kiroagent/`` em 2026-05-27,
com IDs sintéticos determinísticos e conteúdo de mensagens redatado.

Layout produzido::

    base/
    ├── kiro.kiroagent/
    │   ├── config.json
    │   ├── profile.json
    │   ├── default/
    │   │   └── f62de366d0006e17ea00a01f6624aabf      (symlink, 44B real)
    │   ├── <profile_hash>/
    │   │   ├── f62de366d0006e17ea00a01f6624aabf      (catálogo executions)
    │   │   └── <chat_session_inner>/
    │   │       ├── <execution_id_1>                  (execution chat)
    │   │       ├── <execution_id_2>                  (execution do_simple)
    │   │       └── ...                               (7 executions total)
    │   └── workspace-sessions/
    │       └── <base64url_workspace>/
    │           ├── sessions.json                     (catálogo workspace)
    │           └── <session_id>.json                 (sessão completa)
    └── User/
        └── globalStorage/
            └── state.vscdb                           (opcional via build_state_vscdb)

Constantes de IDs sintéticos exportadas para uso direto em testes.
"""
from __future__ import annotations

import json
from pathlib import Path

from kiro_dash.backends.workspace_codec import encode

# IDs sintéticos determinísticos (não correspondem a nada real)
SESSION_ID = "5e551001-1111-1111-1111-111111111111"
DEFAULT_WORKSPACE_PATH = "/home/test/workspace-fixture"
DEFAULT_PROFILE_HASH = "0000000000000000000000000000000a"
INNER_HASH = "11111111111111111111111111111111"  # subdir dentro do profile
CATALOG_FILENAME = "f62de366d0006e17ea00a01f6624aabf"

EXEC_CHAT = "ec000001-c4a7-c4a7-c4a7-000000000001"
EXEC_DO_SIMPLE = "ec000002-d050-d050-d050-000000000002"
EXEC_DO_COMPLEX = "ec000003-d0c0-d0c0-d0c0-000000000003"
EXEC_DO_WRITE = "ec000004-d0e7-d0e7-d0e7-000000000004"
EXEC_SPEC_DISPATCH = "ec000005-5beb-5beb-5beb-000000000005"
EXEC_SPEC_GENERATION = "ec000006-5be6-5be6-5be6-000000000006"
EXEC_RUNNING = "ec000007-1ee0-1ee0-1ee0-000000000007"

# Base timestamp: 2026-05-27 12:00:00 UTC = 1779912000000
T_BASE = 1779912000000


def _intent_action(action_id: str, classification: str, t: int) -> dict:
    return {
        "type": "AgentExecutionAction",
        "actionId": action_id,
        "actionType": "intentClassification",
        "actionState": "Success",
        "chatSessionId": SESSION_ID,
        "emittedAt": t,
        "intentResult": {
            "classification": classification,
            "finalIntent": {"type": classification, "confidence": 0.9},
            "llmIntent": {"type": classification},
            "localIntent": {"type": classification},
        },
    }


def _model_action(action_id: str, t: int, end_t: int) -> dict:
    return {
        "type": "AgentExecutionAction",
        "actionId": action_id,
        "actionType": "model",
        "actionState": "Success",
        "chatSessionId": SESSION_ID,
        "emittedAt": end_t,
        "endTime": end_t,
    }


def _say_action(action_id: str, t: int) -> dict:
    return {
        "type": "AgentExecutionAction",
        "actionId": action_id,
        "actionType": "say",
        "actionState": "Success",
        "chatSessionId": SESSION_ID,
        "emittedAt": t,
        "output": {"message": "<redacted assistant message>"},
    }


def _run_command_action(action_id: str, t: int) -> dict:
    return {
        "type": "AgentExecutionAction",
        "actionId": f"run_command_tooluse_{action_id}",
        "actionType": "runCommand",
        "actionState": "Success",
        "chatSessionId": SESSION_ID,
        "emittedAt": t,
        "toolOrigin": "acp",
        "input": {
            "command": "<redacted command>",
            "cwd": "<redacted cwd>",
            "terminalId": "term-1",
        },
        "rawInput": {
            "command": "<redacted>",
            "cwd": "<redacted>",
            "explanation": "<redacted>",
            "skipPruning": False,
        },
        "output": {"exitCode": 0, "output": "<redacted command output>"},
    }


def _read_files_action(action_id: str, t: int) -> dict:
    return {
        "type": "AgentExecutionAction",
        "actionId": f"tooluse_{action_id}",
        "actionType": "readFiles",
        "actionState": "Accepted",
        "chatSessionId": SESSION_ID,
        "emittedAt": t,
        "toolOrigin": "acp",
        "input": {"files": ["<redacted path>"]},
        "rawInput": {
            "paths": ["<redacted>"],
            "start_line": 1,
            "end_line": 100,
            "explanation": "<redacted>",
            "skipPruning": False,
        },
    }


def _control_process_action(action_id: str, t: int) -> dict:
    return {
        "type": "AgentExecutionAction",
        "actionId": f"start_process_tooluse_{action_id}",
        "actionType": "controlProcess",
        "actionState": "Success",
        "chatSessionId": SESSION_ID,
        "emittedAt": t,
        "toolOrigin": "acp",
        "input": {"action": "start", "command": "<redacted>", "cwd": "<redacted>"},
        "rawInput": {"action": "start", "command": "<redacted>", "cwd": "<redacted>"},
        "output": {"processId": "p-1", "success": True},
    }


def _get_process_output_action(action_id: str, t: int) -> dict:
    return {
        "type": "AgentExecutionAction",
        "actionId": f"tooluse_{action_id}",
        "actionType": "getProcessOutput",
        "actionState": "Success",
        "chatSessionId": SESSION_ID,
        "emittedAt": t,
        "toolOrigin": "acp",
        "input": {"processId": "p-1"},
        "rawInput": {"terminalId": "term-1", "explanation": "<redacted>", "skipPruning": False},
        "output": {"command": "<redacted>", "output": "<redacted>", "path": "<redacted>"},
    }


def _create_action(action_id: str, t: int) -> dict:
    return {
        "type": "AgentExecutionAction",
        "actionId": f"tooluse_{action_id}",
        "actionType": "create",
        "actionState": "Success",
        "chatSessionId": SESSION_ID,
        "emittedAt": t,
        "toolOrigin": "acp",
        "input": {"path": "<redacted>", "fileText": "<redacted>"},
        "rawInput": {"path": "<redacted>", "fileText": "<redacted>"},
        "output": {"success": True},
    }


def _replace_action(action_id: str, t: int) -> dict:
    return {
        "type": "AgentExecutionAction",
        "actionId": f"tooluse_{action_id}",
        "actionType": "replace",
        "actionState": "Success",
        "chatSessionId": SESSION_ID,
        "emittedAt": t,
        "toolOrigin": "acp",
        "input": {"path": "<redacted>", "oldStr": "<redacted>", "newStr": "<redacted>"},
        "rawInput": {"path": "<redacted>", "oldStr": "<redacted>", "newStr": "<redacted>"},
        "output": {"success": True},
    }


def _get_diagnostics_action(action_id: str, t: int) -> dict:
    return {
        "type": "AgentExecutionAction",
        "actionId": f"tooluse_{action_id}",
        "actionType": "getDiagnostics",
        "actionState": "Success",
        "chatSessionId": SESSION_ID,
        "emittedAt": t,
        "toolOrigin": "acp",
        "input": {"paths": ["<redacted>"]},
        "rawInput": {"paths": ["<redacted>"]},
        "output": {"diagnostics": []},
    }


def _spec_agent_action(action_id: str, t: int) -> dict:
    return {
        "type": "AgentExecutionAction",
        "actionId": action_id,
        "actionType": "specAgent",
        "actionState": "Success",
        "chatSessionId": SESSION_ID,
        "emittedAt": t,
        "output": {"specId": "spec-1"},
    }


def _user_input_action(action_id: str, t: int) -> dict:
    return {
        "type": "AgentExecutionAction",
        "actionId": action_id,
        "actionType": "userInput",
        "actionState": "Success",
        "chatSessionId": SESSION_ID,
        "emittedAt": t,
        "input": {"message": "<redacted user input>"},
    }


def _invoke_subagent_action(action_id: str, t: int) -> dict:
    return {
        "type": "AgentExecutionAction",
        "actionId": f"tooluse_{action_id}",
        "actionType": "invokeSubAgent",
        "actionState": "Success",
        "chatSessionId": SESSION_ID,
        "emittedAt": t,
        "toolOrigin": "acp",
        "input": {"agent": "spec-requirements"},
        "rawInput": {"agent": "spec-requirements", "input": "<redacted>"},
        "output": {"success": True},
    }


def _subagent_response_action(action_id: str, t: int) -> dict:
    return {
        "type": "AgentExecutionAction",
        "actionId": action_id,
        "actionType": "subagent_response",
        "actionState": "Success",
        "chatSessionId": SESSION_ID,
        "emittedAt": t,
        "output": {"agent": "spec-requirements", "response": "<redacted>"},
    }


def _execution_envelope(
    *,
    execution_id: str,
    workflow_type: str,
    actions: list[dict],
    usage_summary: list[dict],
    status: str = "succeed",
    start_time: int,
    end_time: int | None,
    autonomy_mode: str = "Autopilot",
    context_usage: float = 1.5,
) -> dict:
    return {
        "executionId": execution_id,
        "workflowType": workflow_type,
        "status": status,
        "startTime": start_time,
        "input": {
            "data": {
                "chatSessionId": SESSION_ID,
                "messages": [{"role": "user", "content": "<redacted>"}],
                "messagesFromExecutionId": [],
            },
            "documents": [],
        },
        "autonomyMode": autonomy_mode,
        "chatSessionId": SESSION_ID,
        "actions": actions,
        "context": {"messages": []},
        "result": {
            "executionId": execution_id,
            "status": "success" if status == "succeed" else status,
            "result": {},
        },
        "endTime": end_time if end_time is not None else 0,
        "usageSummary": usage_summary,
        "contextUsagePercentage": context_usage,
    }


def _build_chat_execution() -> dict:
    """chat-agent intent=chat, 3 actions, ~0.094 cr."""
    t0 = T_BASE
    actions = [
        _intent_action("intent-1", "chat", t0 + 100),
        _model_action("model-1", t0 + 100, t0 + 1500),
        _say_action("say-1", t0 + 1700),
    ]
    usage = [{"usage": 0.094, "unit": "credit", "unitPlural": "credits"}]
    return _execution_envelope(
        execution_id=EXEC_CHAT,
        workflow_type="chat-agent",
        actions=actions,
        usage_summary=usage,
        start_time=t0,
        end_time=t0 + 1700,
    )


def _build_do_simple_execution() -> dict:
    """chat-agent intent=do, 5 actions, ~0.146 cr, tools=[execute_bash]."""
    t0 = T_BASE + 10000
    actions = [
        _intent_action("intent-2", "do", t0 + 100),
        _model_action("model-2a", t0 + 100, t0 + 1500),
        _run_command_action("run-1", t0 + 2000),
        _model_action("model-2b", t0 + 2000, t0 + 3500),
        _say_action("say-2", t0 + 3700),
    ]
    usage = [
        {"usage": 0.020, "unit": "credit", "unitPlural": "credits"},
        {"usedTools": ["execute_bash"], "usage": 0.119, "unit": "credit", "unitPlural": "credits"},
        {"usage": 0.007, "unit": "credit", "unitPlural": "credits"},
    ]
    return _execution_envelope(
        execution_id=EXEC_DO_SIMPLE,
        workflow_type="chat-agent",
        actions=actions,
        usage_summary=usage,
        start_time=t0,
        end_time=t0 + 3700,
    )


def _build_do_complex_execution() -> dict:
    """chat-agent intent=do, 18 actions, ~0.66 cr.

    Cobre process control: read + bash + control + getoutput.
    """
    t0 = T_BASE + 20000
    actions = [
        _intent_action("intent-3", "do", t0 + 100),
        _model_action("model-3a", t0 + 100, t0 + 1500),
        _read_files_action("readf-1", t0 + 2000),
        _model_action("model-3b", t0 + 2200, t0 + 3500),
        _say_action("say-3a", t0 + 3700),
        _run_command_action("run-2", t0 + 4000),
        _model_action("model-3c", t0 + 4200, t0 + 5500),
        _say_action("say-3b", t0 + 5700),
        _run_command_action("run-3", t0 + 6000),
        _model_action("model-3d", t0 + 6200, t0 + 7500),
        _say_action("say-3c", t0 + 7700),
        _control_process_action("ctrl-1", t0 + 8000),
        _model_action("model-3e", t0 + 8200, t0 + 9500),
        _get_process_output_action("getout-1", t0 + 10000),
        _model_action("model-3f", t0 + 10200, t0 + 11500),
        _get_process_output_action("getout-2", t0 + 12000),
        _model_action("model-3g", t0 + 12200, t0 + 13500),
        _say_action("say-3d", t0 + 13700),
    ]
    usage = [
        {"usage": 0.008, "unit": "credit", "unitPlural": "credits"},
        {"usedTools": ["read_files"], "usage": 0.099, "unit": "credit", "unitPlural": "credits"},
        {"usedTools": ["execute_bash"], "usage": 0.119, "unit": "credit", "unitPlural": "credits"},
        {"usedTools": ["execute_bash"], "usage": 0.120, "unit": "credit", "unitPlural": "credits"},
        {"usedTools": ["control_bash_process"], "usage": 0.118, "unit": "credit", "unitPlural": "credits"},
        {"usedTools": ["get_process_output"], "usage": 0.065, "unit": "credit", "unitPlural": "credits"},
        {"usedTools": ["get_process_output"], "usage": 0.068, "unit": "credit", "unitPlural": "credits"},
        {"usage": 0.063, "unit": "credit", "unitPlural": "credits"},
    ]
    return _execution_envelope(
        execution_id=EXEC_DO_COMPLEX,
        workflow_type="chat-agent",
        actions=actions,
        usage_summary=usage,
        start_time=t0,
        end_time=t0 + 13700,
        context_usage=3.29,
    )


def _build_do_write_execution() -> dict:
    """chat-agent intent=do, ~7 actions, fs_write/str_replace/getDiagnostics."""
    t0 = T_BASE + 50000
    actions = [
        _intent_action("intent-4", "do", t0 + 100),
        _model_action("model-4a", t0 + 100, t0 + 1500),
        _read_files_action("readf-2", t0 + 2000),
        _model_action("model-4b", t0 + 2200, t0 + 3500),
        _create_action("crt-1", t0 + 4000),
        _replace_action("rep-1", t0 + 5000),
        _get_diagnostics_action("diag-1", t0 + 6000),
        _model_action("model-4c", t0 + 6200, t0 + 7500),
        _say_action("say-4", t0 + 7700),
    ]
    usage = [
        {"usage": 0.010, "unit": "credit", "unitPlural": "credits"},
        {"usedTools": ["read_file"], "usage": 0.099, "unit": "credit", "unitPlural": "credits"},
        {"usedTools": ["fs_write"], "usage": 0.150, "unit": "credit", "unitPlural": "credits"},
        {"usedTools": ["str_replace"], "usage": 0.120, "unit": "credit", "unitPlural": "credits"},
        {"usedTools": ["getDiagnostics"], "usage": 0.080, "unit": "credit", "unitPlural": "credits"},
        {"usage": 0.040, "unit": "credit", "unitPlural": "credits"},
    ]
    return _execution_envelope(
        execution_id=EXEC_DO_WRITE,
        workflow_type="chat-agent",
        actions=actions,
        usage_summary=usage,
        start_time=t0,
        end_time=t0 + 7700,
    )


def _build_spec_dispatch_execution() -> dict:
    """chat-agent intent=spec, 4 actions, ~0.008 cr.

    Apenas dispatcha para specAgent — trabalho real está em
    EXEC_SPEC_GENERATION.
    """
    t0 = T_BASE + 70000
    actions = [
        _intent_action("intent-5", "spec", t0 + 100),
        _model_action("model-5", t0 + 100, t0 + 800),
        _spec_agent_action("specag-1", t0 + 1000),
        _user_input_action("ui-1", t0 + 1100),
    ]
    usage = [{"usage": 0.008, "unit": "credit", "unitPlural": "credits"}]
    return _execution_envelope(
        execution_id=EXEC_SPEC_DISPATCH,
        workflow_type="chat-agent",
        actions=actions,
        usage_summary=usage,
        start_time=t0,
        end_time=t0 + 1100,
    )


def _build_spec_generation_execution() -> dict:
    """workflow=spec-generation, 10 actions, ~0.5 cr.

    Sub-execução disparada por spec-dispatch acima. Sem
    intentClassification (sub-execuções não passam por classifier).
    """
    t0 = T_BASE + 71000
    actions = [
        _model_action("model-6a", t0, t0 + 2000),
        _invoke_subagent_action("sub-1", t0 + 2200),
        _subagent_response_action("subr-1", t0 + 5000),
        _model_action("model-6b", t0 + 5200, t0 + 6500),
        _create_action("crt-2", t0 + 7000),
        _create_action("crt-3", t0 + 8000),
        _create_action("crt-4", t0 + 9000),
        _model_action("model-6c", t0 + 9200, t0 + 10500),
        _say_action("say-6", t0 + 10700),
    ]
    usage = [
        {"usage": 0.030, "unit": "credit", "unitPlural": "credits"},
        {"usedTools": ["invoke_sub_agent"], "usage": 0.180, "unit": "credit", "unitPlural": "credits"},
        {"usedTools": ["subagent_response"], "usage": 0.020, "unit": "credit", "unitPlural": "credits"},
        {"usedTools": ["fs_write"], "usage": 0.100, "unit": "credit", "unitPlural": "credits"},
        {"usedTools": ["fs_write"], "usage": 0.090, "unit": "credit", "unitPlural": "credits"},
        {"usedTools": ["fs_write"], "usage": 0.080, "unit": "credit", "unitPlural": "credits"},
        {"usage": 0.050, "unit": "credit", "unitPlural": "credits"},
    ]
    return _execution_envelope(
        execution_id=EXEC_SPEC_GENERATION,
        workflow_type="spec-generation",
        actions=actions,
        usage_summary=usage,
        start_time=t0,
        end_time=t0 + 10700,
    )


def _build_running_execution() -> dict:
    """workflow=spec-generation, status=running, endTime=0.

    Heurística "live" da T9 detecta esta execution.
    """
    t0 = T_BASE + 90000
    actions = [
        _model_action("model-7", t0, t0 + 1000),
        _invoke_subagent_action("sub-2", t0 + 1200),
    ]
    usage = [
        {"usage": 0.020, "unit": "credit", "unitPlural": "credits"},
        {"usedTools": ["invoke_sub_agent"], "usage": 0.100, "unit": "credit", "unitPlural": "credits"},
    ]
    return _execution_envelope(
        execution_id=EXEC_RUNNING,
        workflow_type="spec-generation",
        actions=actions,
        usage_summary=usage,
        status="running",
        start_time=t0,
        end_time=None,  # endTime: 0 indica running
    )


def _build_session_json(workspace_path: str = DEFAULT_WORKSPACE_PATH) -> dict:
    """Sessão completa redatada (history sem conteúdo)."""
    return {
        "sessionId": SESSION_ID,
        "title": "Test Fixture Session",
        "dateCreated": str(T_BASE),
        "workspaceDirectory": workspace_path,
        "sessionType": "vibe",
        "autonomyMode": "Autopilot",
        "selectedModel": "auto",
        "defaultModelTitle": "Agent",
        "history": [
            {
                "message": "<redacted user message 1>",
                "contextItems": [],
                "editorState": {"<redacted>": True},
            },
            {
                "message": "<redacted assistant response 1>",
                "contextItems": [],
                "editorState": {"<redacted>": True},
            },
        ],
        "contextUsagePercentage": 3.29,
        "contextUsagePercentageBySession": {SESSION_ID: 3.29},
    }


def _build_executions_catalog() -> dict:
    """Catálogo de executions com 7 entries: 6 succeed, 1 running."""
    cases = [
        (EXEC_CHAT, "chat-agent", "succeed", T_BASE, T_BASE + 1700),
        (EXEC_DO_SIMPLE, "chat-agent", "succeed", T_BASE + 10000, T_BASE + 13700),
        (EXEC_DO_COMPLEX, "chat-agent", "succeed", T_BASE + 20000, T_BASE + 33700),
        (EXEC_DO_WRITE, "chat-agent", "succeed", T_BASE + 50000, T_BASE + 57700),
        (EXEC_SPEC_DISPATCH, "chat-agent", "succeed", T_BASE + 70000, T_BASE + 71100),
        (EXEC_SPEC_GENERATION, "spec-generation", "succeed", T_BASE + 71000, T_BASE + 81700),
        (EXEC_RUNNING, "spec-generation", "running", T_BASE + 90000, 0),
    ]
    executions = []
    for exec_id, wtype, status, start, end in cases:
        executions.append(
            {
                "executionId": exec_id,
                "type": wtype,
                "status": status,
                "startTime": start,
                "endTime": end,
                "chatSessionId": SESSION_ID,
            }
        )
    return {"executions": executions}


def _build_sessions_catalog(workspace_path: str = DEFAULT_WORKSPACE_PATH) -> list[dict]:
    """Catálogo workspace-sessions/<b64>/sessions.json."""
    return [
        {
            "sessionId": SESSION_ID,
            "title": "Test Fixture Session",
            "dateCreated": str(T_BASE),
            "workspaceDirectory": workspace_path,
        }
    ]


# ── builder principal ────────────────────────────────────────────────


def build_ide_layout(
    base_dir: Path,
    *,
    workspace_path: str = DEFAULT_WORKSPACE_PATH,
    profile_hash: str = DEFAULT_PROFILE_HASH,
    include_running: bool = True,
    extra_workspaces: list[str] | None = None,
    extra_profile_hashes: list[str] | None = None,
) -> Path:
    """Constrói árvore IDE redatada em ``base_dir``.

    Retorna o ``Path`` do diretório ``kiro.kiroagent`` raiz.

    :param base_dir: diretório-base (tipicamente ``tmp_path``)
    :param workspace_path: caminho lógico do workspace (será codificado em base64url)
    :param profile_hash: hash do profile principal
    :param include_running: se True, inclui ``EXEC_RUNNING`` (status=running)
    :param extra_workspaces: workspaces adicionais (testar multi-workspace)
    :param extra_profile_hashes: profile hashes adicionais (testar multi-profile)
    """
    kiro_root = base_dir / "kiro.kiroagent"
    kiro_root.mkdir(parents=True, exist_ok=True)

    # config.json e profile.json (não-críticos, só presença)
    (kiro_root / "config.json").write_text(json.dumps({"version": 1}))
    (kiro_root / "profile.json").write_text(json.dumps({"profileHash": profile_hash}))

    # Profile dirs
    profile_hashes = [profile_hash] + (extra_profile_hashes or [])
    for ph in profile_hashes:
        ph_dir = kiro_root / ph
        ph_dir.mkdir(exist_ok=True)

        # Catálogo de executions
        catalog = _build_executions_catalog()
        if not include_running:
            catalog["executions"] = [
                e for e in catalog["executions"] if e["status"] != "running"
            ]
        (ph_dir / CATALOG_FILENAME).write_text(json.dumps(catalog, ensure_ascii=False))

        # Subdir interno onde ficam os arquivos de execution completos
        inner = ph_dir / INNER_HASH
        inner.mkdir(exist_ok=True)

        execs = [
            (EXEC_CHAT, _build_chat_execution()),
            (EXEC_DO_SIMPLE, _build_do_simple_execution()),
            (EXEC_DO_COMPLEX, _build_do_complex_execution()),
            (EXEC_DO_WRITE, _build_do_write_execution()),
            (EXEC_SPEC_DISPATCH, _build_spec_dispatch_execution()),
            (EXEC_SPEC_GENERATION, _build_spec_generation_execution()),
        ]
        if include_running:
            execs.append((EXEC_RUNNING, _build_running_execution()))

        for exec_id, payload in execs:
            (inner / exec_id).write_text(json.dumps(payload, ensure_ascii=False))

    # default/ symlink — só presença, conteúdo dummy de 44B
    default_dir = kiro_root / "default"
    default_dir.mkdir(exist_ok=True)
    (default_dir / CATALOG_FILENAME).write_text(
        json.dumps({"profileHash": profile_hash})  # placeholder, ~30B
    )

    # workspace-sessions
    ws_root = kiro_root / "workspace-sessions"
    ws_root.mkdir(exist_ok=True)

    workspaces = [workspace_path] + (extra_workspaces or [])
    for wp in workspaces:
        wp_b64 = encode(wp)
        wp_dir = ws_root / wp_b64
        wp_dir.mkdir(exist_ok=True)
        (wp_dir / "sessions.json").write_text(
            json.dumps(_build_sessions_catalog(wp), ensure_ascii=False)
        )
        (wp_dir / f"{SESSION_ID}.json").write_text(
            json.dumps(_build_session_json(wp), ensure_ascii=False)
        )

    return kiro_root
