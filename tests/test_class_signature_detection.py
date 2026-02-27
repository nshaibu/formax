import typing
import inspect
import pytest
from dataclasses import dataclass, field
from enum import Enum

from formax.fields import _ClassSignatureMatcher


@pytest.mark.parametrize("cls", [int, str, float, list, dict])
def test_builtin_types(cls):
    m = _ClassSignatureMatcher(cls)

    assert m.required == frozenset()
    assert m.allowed == frozenset()
    assert m.has_kwargs is False
    assert bool(m) is False


def test_typing_any():
    m = _ClassSignatureMatcher(typing.Any)

    assert m.required == frozenset()
    assert m.allowed == frozenset()
    assert m.has_kwargs is False
    assert bool(m) is False


def test_enum_subclass():
    class Color(Enum):
        RED = 1
        BLUE = 2

    m = _ClassSignatureMatcher(Color)

    assert m.required == frozenset()
    assert m.allowed == frozenset()
    assert m.has_kwargs is False
    assert bool(m) is False


def test_dataclass_required_and_optional_fields():
    @dataclass
    class Model:
        a: int
        b: int = 1
        c: str = field(default_factory=str)

    m = _ClassSignatureMatcher(Model)

    assert m.allowed == frozenset({"a", "b", "c"})
    assert m.required == frozenset({"a"})
    assert m.has_kwargs is False
    assert bool(m) is True


def test_dataclass_all_optional():
    @dataclass
    class Model:
        a: int = 1
        b: int = 2

    m = _ClassSignatureMatcher(Model)

    assert m.allowed == frozenset({"a", "b"})
    assert m.required == frozenset()
    assert m.has_kwargs is False
    assert bool(m) is True  # allowed is non-empty


def test_simple_class_signature():
    class Model:
        def __init__(self, a, b=1):
            pass

    m = _ClassSignatureMatcher(Model)

    assert m.allowed == frozenset({"a", "b"})
    assert m.required == frozenset({"a"})
    assert m.has_kwargs is False
    assert bool(m) is True


def test_class_with_kwargs():
    class Model:
        def __init__(self, a, **kwargs):
            pass

    m = _ClassSignatureMatcher(Model)

    assert m.allowed == frozenset({"a", "kwargs"})
    assert m.required == frozenset({"a"})
    assert m.has_kwargs is True
    assert bool(m) is True


def test_class_with_args_and_kwargs():
    class Model:
        def __init__(self, *args, **kwargs):
            pass

    m = _ClassSignatureMatcher(Model)

    # *args and **kwargs are allowed, but not required
    assert m.allowed == frozenset({"args", "kwargs"})
    assert m.required == frozenset({})
    assert m.has_kwargs is True
    assert bool(m) is True


def test_signature_failure_fallback(monkeypatch):
    class Broken:
        pass

    def raise_type_error(*args, **kwargs):
        raise TypeError

    monkeypatch.setattr(inspect, "signature", raise_type_error)

    m = _ClassSignatureMatcher(Broken)

    assert m.required == frozenset()
    assert m.allowed == frozenset()
    assert m.has_kwargs is False
    assert bool(m) is False


def test_bool_false_when_empty():
    class Empty:
        pass

    m = _ClassSignatureMatcher(Empty)

    assert m.required == frozenset()
    assert m.allowed == frozenset()
    assert bool(m) is False


def test_bool_true_when_allowed_only():
    class Model:
        def __init__(self, a=1):
            pass

    m = _ClassSignatureMatcher(Model)

    assert m.required == frozenset()
    assert m.allowed
    assert bool(m) is True
