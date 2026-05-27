"""Tests de ``backends.workspace_codec``."""
from __future__ import annotations

import pytest

from kiro_dash.backends.workspace_codec import decode, encode


def test_encode_real_observed_path():
    """Caso real observado em 2026-05-27."""
    path = "/home/menzani/Desenvolvimento/mencoding/cvat-adeptus"
    expected = "L2hvbWUvbWVuemFuaS9EZXNlbnZvbHZpbWVudG8vbWVuY29kaW5nL2N2YXQtYWRlcHR1cw__"
    assert encode(path) == expected


def test_decode_real_observed_path():
    encoded = "L2hvbWUvbWVuemFuaS9EZXNlbnZvbHZpbWVudG8vbWVuY29kaW5nL2N2YXQtYWRlcHR1cw__"
    assert decode(encoded) == "/home/menzani/Desenvolvimento/mencoding/cvat-adeptus"


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/home",
        "/home/test",
        "/home/test/workspace",
        "/a",
        "/a/b/c/d/e/f/g/h/i/j",
        "/path/with spaces/and/sub",
        "/path/with/unicode/café",
        "/path/with/emoji/🚀",
        "/path/with-dashes/and_underscores",
        "/" + "x" * 200,  # path longo
    ],
)
def test_roundtrip(path):
    assert decode(encode(path)) == path


def test_encode_empty_string():
    assert encode("") == ""
    assert decode("") == ""


def test_encode_padding_replacement():
    """Confirma que ``=`` nunca aparece no encoded e é sempre ``_``."""
    # Strings de comprimentos diversos para forçar padding 0/1/2 chars
    for n in range(1, 10):
        encoded = encode("x" * n)
        assert "=" not in encoded
        assert decode(encoded) == "x" * n


def test_decode_invalid_base64_raises():
    with pytest.raises(ValueError, match="base64url"):
        decode("not!valid!base64")


def test_decode_non_utf8_raises():
    """Bytes válidos em base64 mas não UTF-8 devem levantar ValueError."""
    # \xff\xfe não é UTF-8 válido
    invalid_utf8_b64 = "__7-"  # base64url de bytes 0xff 0xfe -> "__7-" tem _
    # Construir manualmente:
    import base64 as _b
    raw = bytes([0xff, 0xfe, 0xfd])
    encoded = _b.urlsafe_b64encode(raw).decode("ascii").replace("=", "_")
    with pytest.raises(ValueError, match="UTF-8"):
        decode(encoded)


def test_encode_type_error():
    with pytest.raises(TypeError):
        encode(b"/home/test")  # type: ignore[arg-type]


def test_decode_type_error():
    with pytest.raises(TypeError):
        decode(b"abc")  # type: ignore[arg-type]


def test_encode_idempotent_for_alphanumeric():
    """Para strings ASCII alfanuméricas simples, encode/decode é estável."""
    s = "/abc/def/ghi"
    e1 = encode(s)
    e2 = encode(s)
    assert e1 == e2
    assert decode(e1) == s
