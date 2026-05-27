"""Redator de sessões IDE para sync seguro (T4-W7).

Sessões do Kiro IDE em
``~/.config/Kiro/User/globalStorage/kiro.kiroagent/workspace-sessions/<b64>/<sid>.json``
contêm conteúdo de mensagens em campos como ``history[].message``,
``actions[].input``, ``actions[].output``, ``actions[].say.message``,
``editorState``, etc. Sincronizar esses arquivos para um remoto
(Google Drive, S3) sem redação vazaria conteúdo de prompts/respostas
cross-device, contrariando o princípio de privacidade.

Este módulo expõe ``redact_session_dict`` e ``redact_executions_dict``
puros (sem I/O), que produzem versões seguras para upload preservando
apenas metadata estrutural: IDs, timestamps, status, modelo,
``usageSummary``, ``intentResult.classification``, contagens.

Vocabulário de redação:

| Campo redatado | Substituição |
|---|---|
| ``history[].message`` | removido |
| ``history[].editorState`` | removido |
| ``history[].contextItems`` | substituído por ``[<count>]`` |
| ``actions[].input.content`` | ``"<redacted>"`` |
| ``actions[].input.fileText`` | ``"<redacted>"`` |
| ``actions[].input.command`` | ``"<redacted>"`` |
| ``actions[].input.message`` | ``"<redacted>"`` |
| ``actions[].input.oldStr`` / ``newStr`` | ``"<redacted>"`` |
| ``actions[].output.content`` | ``"<redacted>"`` |
| ``actions[].output.message`` | ``"<redacted>"`` |
| ``actions[].output.output`` | ``"<redacted>"`` |
| ``actions[].say.output.message`` | ``"<redacted>"`` |
| ``actions[].rawInput`` | removido inteiro |
| ``input.data.messages[].content`` | ``"<redacted>"`` |
| ``context.messages[].content`` | ``"<redacted>"`` |
| ``title`` (sessão) | preservado (gerado por LLM, considerado low-risk; usuário pode optar por redação extra via flag, futuro) |
"""
from __future__ import annotations

import copy
from typing import Any

REDACTED = "<redacted>"
"""Placeholder padrão para campos de conteúdo."""


# Campos sensíveis dentro de input/output de actions
_INPUT_SENSITIVE_KEYS = {
    "content",
    "fileText",
    "command",
    "message",
    "oldStr",
    "newStr",
    "input",  # quando é string ou dict-com-content
}
_OUTPUT_SENSITIVE_KEYS = {
    "content",
    "message",
    "output",  # comum em runCommand/getProcessOutput
    "response",
}


def _redact_input_dict(d: Any) -> Any:
    """Redata recursivamente campos sensíveis em ``input`` ou similar."""
    if isinstance(d, dict):
        out: dict = {}
        for k, v in d.items():
            if k in _INPUT_SENSITIVE_KEYS and isinstance(v, str) and v:
                out[k] = REDACTED
            elif isinstance(v, (dict, list)):
                out[k] = _redact_input_dict(v)
            else:
                out[k] = v
        return out
    if isinstance(d, list):
        return [_redact_input_dict(x) for x in d]
    return d


def _redact_output_dict(d: Any) -> Any:
    """Redata recursivamente campos sensíveis em ``output``."""
    if isinstance(d, dict):
        out: dict = {}
        for k, v in d.items():
            if k in _OUTPUT_SENSITIVE_KEYS and isinstance(v, str) and v:
                out[k] = REDACTED
            elif isinstance(v, (dict, list)):
                out[k] = _redact_output_dict(v)
            else:
                out[k] = v
        return out
    if isinstance(d, list):
        return [_redact_output_dict(x) for x in d]
    return d


def redact_action(action: dict) -> dict:
    """Redata um ``action`` individual.

    Preserva ``actionId``/``actionType``/``actionState``/``emittedAt``/
    ``executionId``/``chatSessionId``/``toolOrigin``/``intentResult``/
    ``endTime`` (estruturais). Filtra ``input``/``output``/``rawInput``.
    """
    out: dict = {}
    for k, v in action.items():
        if k == "rawInput":
            continue  # remover inteiro
        if k == "input":
            out[k] = _redact_input_dict(v)
        elif k == "output":
            out[k] = _redact_output_dict(v)
        else:
            out[k] = v
    return out


def redact_history_item(item: dict) -> dict:
    """Redata um item de ``history[]`` da sessão."""
    out: dict = {}
    ctx_items = item.get("contextItems") or []
    for k, v in item.items():
        if k == "message":
            continue  # remover mensagem
        if k == "editorState":
            continue  # remover estado do editor (pode conter texto)
        if k == "contextItems":
            # preservar shape mas zerar conteúdo
            out[k] = [
                {"<count>": len(ctx_items) if isinstance(ctx_items, list) else 0}
            ]
        else:
            out[k] = v
    return out


def redact_session_dict(session: dict) -> dict:
    """Redata um JSON de sessão IDE inteiro para sync seguro.

    Não muta o original — retorna deep-copy modificado.
    """
    safe = copy.deepcopy(session)
    if "history" in safe and isinstance(safe["history"], list):
        safe["history"] = [
            redact_history_item(h) if isinstance(h, dict) else {}
            for h in safe["history"]
        ]
    return safe


def redact_execution_dict(execution: dict) -> dict:
    """Redata um JSON de execution inteiro para sync seguro.

    Filtra ``actions[]``, ``input.data.messages``, ``context.messages``
    e ``result.result.content`` se presente.
    """
    safe = copy.deepcopy(execution)
    if "actions" in safe and isinstance(safe["actions"], list):
        safe["actions"] = [
            redact_action(a) if isinstance(a, dict) else {}
            for a in safe["actions"]
        ]
    # input.data.messages
    inp = safe.get("input") or {}
    if isinstance(inp, dict):
        data = inp.get("data") or {}
        if isinstance(data, dict):
            msgs = data.get("messages") or []
            if isinstance(msgs, list):
                data["messages"] = [
                    {"role": m.get("role", "?"), "content": REDACTED}
                    if isinstance(m, dict)
                    else m
                    for m in msgs
                ]
    # context.messages
    ctx = safe.get("context") or {}
    if isinstance(ctx, dict):
        ctx_msgs = ctx.get("messages") or []
        if isinstance(ctx_msgs, list):
            ctx["messages"] = [
                {"role": m.get("role", "?"), "content": REDACTED}
                if isinstance(m, dict)
                else m
                for m in ctx_msgs
            ]
    # result.result.content (raro mas defensivo)
    result = safe.get("result") or {}
    if isinstance(result, dict):
        inner = result.get("result")
        if isinstance(inner, dict) and "content" in inner:
            inner["content"] = REDACTED
    return safe
