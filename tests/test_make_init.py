import types
import pytest
import inspect
from dataclasses import MISSING

from pydantic_mini.make_init import (
    join_string,
    make_disable_all_validation_init,
    make_disable_type_check_init,
    make_fast_init,
)
from pydantic_mini.utils import make_private_field


class DummyQuery:
    def __init__(self):
        self.calls = []

    def validate(self, value, field_name):
        self.calls.append((value, field_name))


class DummyMiniField:
    def __init__(
        self,
        default=MISSING,
        preformat=None,
        validator=None,
        query=None,
    ):
        self._default = default
        self._preformat_callback = preformat
        self._field_validator = validator
        self._query = query or DummyQuery()

        # fast-init internals
        self.expected_type = types.SimpleNamespace(module_context=None)
        self.inner_type = None

    def get_default(self):
        return self._default

    def run_preformatters(self, instance, value):
        if self._preformat_callback:
            return self._preformat_callback(instance, value)
        return value

    def run_validators(self, instance, value):
        if self._field_validator:
            self._field_validator(instance, value)

    def get_model_context(self, instance):
        return {"model": instance}

    def _finalise_type_resolver(self):
        pass

    def _value_coerce(self, value):
        return None

    def _field_type_validator(self, value):
        pass


def test_join_string_empty():
    assert join_string([]) == ""


def test_join_string_single():
    assert join_string(["a"]) == "a,"


def test_join_string_multiple():
    assert join_string(["a", "b"]) == "a,b,"


def test_disable_all_validation_init_sets_private_fields():
    attrs = {
        "__annotations__": {"x": int, "y": int},
        "x": DummyMiniField(),
        "y": DummyMiniField(),
    }

    init = make_disable_all_validation_init(attrs)

    class Model:
        pass

    Model.__init__ = init

    m = Model(1, 2)

    assert m.__dict__[make_private_field("x")] == 1
    assert m.__dict__[make_private_field("y")] == 2


def test_disable_all_validation_runs_preformatter():
    def pre(instance, v):
        return v + 1

    attrs = {
        "__annotations__": {"x": int},
        "x": DummyMiniField(preformat=pre),
    }

    init = make_disable_all_validation_init(attrs)

    class Model:
        pass

    Model.__init__ = init

    m = Model(10)

    assert m.__dict__[make_private_field("x")] == 11


def test_disable_type_check_runs_query_and_validator():
    query = DummyQuery()
    calls = []

    def validator(instance, value):
        calls.append(value)

    attrs = {
        "__annotations__": {"x": int},
        "x": DummyMiniField(
            validator=validator,
            query=query,
        ),
    }

    init = make_disable_type_check_init(attrs)

    class Model:
        pass

    Model.__init__ = init

    m = Model(5)

    assert calls == [5]
    assert query.calls == [(5, "x")]
    assert m.__dict__[make_private_field("x")] == 5


def test_fast_init_assigns_private_fields():
    attrs = {
        "__annotations__": {"x": int},
        "x": DummyMiniField(),
    }

    init = make_fast_init(attrs)

    class Model:
        pass

    Model.__init__ = init

    m = Model(42)

    assert m.__dict__[make_private_field("x")] == 42

def test_fast_init_runs_full_pipeline():
    calls = []

    def pre(instance, v):
        return v * 2

    def validator(instance, v):
        calls.append(v)

    attrs = {
        "__annotations__": {"x": int},
        "x": DummyMiniField(
            preformat=pre,
            validator=validator,
        ),
    }

    init = make_fast_init(attrs)

    class Model:
        pass

    Model.__init__ = init

    m = Model(3)

    assert calls == [6]
    assert m.__dict__[make_private_field("x")] == 6


def test_generated_init_signature_required_vs_default():
    attrs = {
        "__annotations__": {"x": int, "y": int},
        "x": DummyMiniField(),
        "y": DummyMiniField(default=10),
    }

    init = make_disable_all_validation_init(attrs)

    sig = str(inspect.signature(init))
    assert "x" in sig
    assert "y=10" in sig
