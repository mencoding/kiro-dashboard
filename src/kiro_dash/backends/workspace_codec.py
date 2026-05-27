"""Codec para nomes de diretório de workspace do Kiro IDE.

O IDE codifica caminhos absolutos como ``base64url`` com o padding ``=``
substituído por ``_``. Exemplo:

    /home/menzani/Desenvolvimento/mencoding/cvat-adeptus
    → L2hvbWUvbWVuemFuaS9EZXNlbnZvbHZpbWVudG8vbWVuY29kaW5nL2N2YXQtYWRlcHR1cw__

Este módulo expõe ``encode``/``decode`` puros (sem I/O), com roundtrip
garantido para qualquer string UTF-8.
"""
from __future__ import annotations

import base64


def encode(path: str) -> str:
    """Codifica caminho em base64url Kiro-compatible.

    Aplica base64url padrão e troca o padding ``=`` (sempre trailing)
    por ``_`` para casar com a convenção observada do IDE. Nota: ``_``
    é caractere válido em base64url (substituto de ``/``); a substituição
    é restrita ao padding final.
    """
    if not isinstance(path, str):
        raise TypeError(f"encode espera str, recebeu {type(path).__name__}")
    raw = path.encode("utf-8")
    encoded = base64.urlsafe_b64encode(raw).decode("ascii")
    no_pad = encoded.rstrip("=")
    return no_pad + ("_" * (len(encoded) - len(no_pad)))


def decode(encoded: str) -> str:
    """Decodifica nome de diretório IDE → caminho original.

    Inverso de ``encode``: ``_`` trailing → ``=`` trailing, e base64url
    padrão. ``_`` no meio é mantido (caractere válido). Levanta
    ``ValueError`` em padding inválido ou bytes não-UTF-8.
    """
    if not isinstance(encoded, str):
        raise TypeError(f"decode espera str, recebeu {type(encoded).__name__}")
    no_pad = encoded.rstrip("_")
    restored = no_pad + ("=" * (len(encoded) - len(no_pad)))
    try:
        raw = base64.urlsafe_b64decode(restored.encode("ascii"))
    except Exception as exc:  # binascii.Error subclass de ValueError
        raise ValueError(f"base64url inválido: {encoded!r}") from exc
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"bytes decodificados não são UTF-8: {encoded!r}") from exc
