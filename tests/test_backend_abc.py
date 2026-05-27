"""Testes da camada de fronteira ``backends`` (ADR-0001)."""
from __future__ import annotations

import pytest

from kiro_dash.backends import Backend, Capability


def test_capability_enum_has_expected_members():
    members = {m.name for m in Capability}
    assert members == {
        "USAGE_STATE",
        "SESSIONS",
        "TURNS",
        "TOOL_CALLS",
        "RUNNING",
        "ACCOUNT",
    }


def test_backend_abc_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        Backend()  # type: ignore[abstract]


def test_subclass_must_implement_abstract_methods():
    class IncompleteBackend(Backend):
        pass

    with pytest.raises(TypeError):
        IncompleteBackend()  # type: ignore[abstract]


def test_minimal_concrete_subclass_works():
    class DummyBackend(Backend):
        @property
        def slug(self) -> str:
            return "dummy"

        def is_available(self) -> bool:
            return True

        def capabilities(self) -> set[Capability]:
            return {Capability.SESSIONS}

    b = DummyBackend()
    assert b.slug == "dummy"
    assert b.is_available() is True
    assert b.capabilities() == {Capability.SESSIONS}
    # data_age() default retorna None
    assert b.data_age() is None


def test_subclass_can_override_data_age():
    class TimedBackend(Backend):
        @property
        def slug(self) -> str:
            return "timed"

        def is_available(self) -> bool:
            return True

        def capabilities(self) -> set[Capability]:
            return {Capability.USAGE_STATE}

        def data_age(self) -> float | None:
            return 42.5

    assert TimedBackend().data_age() == 42.5
