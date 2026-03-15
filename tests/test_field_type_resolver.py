import pytest
import dataclasses
from enum import Enum

from formax.typing import ModelConfigWrapper, ValidationFlags
from formax.fields import _ExpectedType, _ExpectedTypeResolver


MISSING = dataclasses.MISSING
dc_fields = dataclasses.fields


class Config:
    validation = ValidationFlags.COERCE


model_config = ModelConfigWrapper(Config)


class Color(Enum):
    RED = 1
    BLUE = 2


@dataclasses.dataclass
class User:
    id: int
    name: str


class FlexibleUser:
    def __init__(self, id: int, name: str, **kwargs):
        self.id = id
        self.name = name
        self.extra = kwargs


class StrictUser:
    def __init__(self, id: int, name: str):
        self.id = id
        self.name = name


def test_resolver_initialization():
    """Ensure resolver fails if no types are provided."""
    with pytest.raises(TypeError, match="No types were provided"):
        _ExpectedTypeResolver((), model_config=model_config)


def test_direct_instance_match():
    resolver = _ExpectedTypeResolver((int, str), model_config=model_config)
    match = resolver.get_matching_type(10)
    assert match.type is int
    assert resolver.coerce(10) == 10


def test_builtin_coercion():
    resolver = _ExpectedTypeResolver((int,), model_config=model_config)
    assert resolver.coerce("123") == 123

    # Order test: Should pick first successful coercion
    resolver_order = _ExpectedTypeResolver((float, int), model_config=model_config)
    result = resolver_order.coerce("123")
    assert isinstance(result, float)


def test_enum_coercion():
    resolver = _ExpectedTypeResolver((Color,), model_config=model_config)
    assert resolver.coerce(Color.RED) == Color.RED
    assert resolver.coerce(1) == Color.RED


def test_dataclass_structural_match():
    resolver = _ExpectedTypeResolver((User, int), model_config=model_config)
    data = {"id": 1, "name": "Alice"}

    match = resolver.get_matching_type(data)
    assert match.type is User

    obj = resolver.coerce(data)
    assert isinstance(obj, User)
    assert obj.name == "Alice"


def test_strict_class_rejection():
    resolver = _ExpectedTypeResolver((StrictUser,), model_config=model_config)
    data = {"id": 1, "name": "Alice", "unexpected": "data"}

    assert resolver.get_matching_type(data) is None
    with pytest.raises(TypeError):
        resolver.coerce(data)


def test_flexible_class_acceptance():
    resolver = _ExpectedTypeResolver((FlexibleUser,), model_config=model_config)
    data = {"id": 1, "name": "Alice", "unexpected": "data"}

    match = resolver.get_matching_type(data)
    assert match.type is FlexibleUser

    obj = resolver.coerce(data)
    assert obj.extra["unexpected"] == "data"


def test_required_parameter_missing():
    resolver = _ExpectedTypeResolver((User,), model_config=model_config)
    data = {"id": 1}  # 'name' is missing

    assert resolver.get_matching_type(data) is None


def test_resolution_failure():
    resolver = _ExpectedTypeResolver((int, Color), model_config=model_config)
    with pytest.raises(
        TypeError, match="Cannot coerce 'str' to any of the type\(s\) 'int, Color'"
    ):
        resolver.coerce("not_an_int_or_enum")


def test_hash_uniqueness():
    et1 = _ExpectedType(int, 0)
    et2 = _ExpectedType(str, 1)
    assert hash(et1) != hash(et2)
