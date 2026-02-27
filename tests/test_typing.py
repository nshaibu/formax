import pytest
import typing
import sys
from typing import List, Optional, Union, Any, ClassVar, ForwardRef
from dataclasses import InitVar, dataclass

from formax.typing import (
    is_mini_annotated,
    is_type,
    is_initvar_type,
    is_class_var_type,
    is_any_type,
    get_type,
    resolve_annotations,
    is_optional_type,
    get_origin,
    is_collection,
    get_forward_type,
    is_builtin_type,
    MiniAnnotated,
    Attrib,
    NoneType,
    Annotated,
)


def test_is_mini_annotated():
    valid = Annotated[int, Attrib()]
    assert is_mini_annotated(valid) is True

    invalid_annotated = Annotated[int, "some string"]
    assert is_mini_annotated(invalid_annotated) is False

    assert is_mini_annotated(int) is None


def test_is_type():
    assert is_type(int) is True
    assert is_type(str) is True
    assert (
        is_type(List[int]) is False
    )  # GenericAlias is not a 'type' instance in older py
    assert is_type("str") is False


def test_is_initvar_type():
    iv = InitVar[int]
    assert is_initvar_type(iv) is True
    assert is_initvar_type(int) is False


def test_is_class_var_type():
    assert is_class_var_type(ClassVar[int]) is True
    assert is_class_var_type(int) is False


def test_is_any_type():
    assert is_any_type(Any) is True
    assert is_any_type(int) is False


def test_is_optional_type():
    assert is_optional_type(Optional[int]) is True
    assert is_optional_type(Union[int, None]) is True
    assert is_optional_type(int) is False


def test_get_type_resolution():
    assert get_type(int) is int
    assert get_type(Optional[int]) is int

    if sys.version_info < (3, 11):
        assert get_type(Any) is object
    else:
        assert get_type(Any) is typing.Any

    assert get_type(List[int]) is list


def test_get_forward_type():
    assert get_forward_type("MyClass") == "MyClass"

    ref = ForwardRef("AnotherClass")
    assert get_forward_type(ref) == "AnotherClass"

    assert get_forward_type(List["Child"]) == "Child"

    # Standard type (not a forward ref)
    assert get_forward_type(int) is None


def test_is_builtin_type():
    assert is_builtin_type(int) is True
    assert is_builtin_type(list) is True

    class MyCustomClass:
        pass

    assert is_builtin_type(MyCustomClass) is False


def test_mini_annotated_logic():
    # Valid usage via __class_getitem__
    ma = MiniAnnotated[int, Attrib(default=5)]

    assert get_origin(ma) is Annotated
    assert ma.__metadata__[0].default == 5

    with pytest.raises(TypeError, match="exactly two arguments"):
        MiniAnnotated[int, Attrib(), "third"]

    with pytest.raises(TypeError, match="must be instance of Attrib"):
        MiniAnnotated[int, "not-an-attrib"]


def test_resolve_annotations_logic():
    class LocalModel:
        a: int
        b: "RemoteClass"

    class RemoteClass:
        pass

    # Passing globals to resolve the forward reference "RemoteClass"
    hints = resolve_annotations(LocalModel, global_ns=locals())
    assert hints["a"] is int
    # If resolve works, this should be the class, not the string
    assert hints["b"] is RemoteClass
