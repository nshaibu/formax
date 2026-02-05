from __future__ import annotations
import re
import logging
import sys
import types
import typing
import inspect
import collections
from dataclasses import MISSING, InitVar

if sys.version_info >= (3, 11):
    from typing import dataclass_transform
else:
    from typing_extensions import dataclass_transform

if sys.version_info < (3, 9):
    from typing_extensions import Annotated, get_origin, get_args, ForwardRef
else:
    from typing import Annotated, get_origin, get_args, ForwardRef

from .exceptions import ValidationError

if typing.TYPE_CHECKING:
    from .base import BaseModel
    from .fields import MiniField

__all__ = (
    "Annotated",
    "MiniAnnotated",
    "evaluate_forward_ref",
    "resolve_and_cache_forward_ref",
    "Attrib",
    "get_type",
    "is_collection",
    "is_optional_type",
    "is_type",
    "is_mini_annotated",
    "NoneType",
    "ModelConfigWrapper",
    "is_builtin_type",
    "InitVar",
    "is_initvar_type",
    "is_class_var_type",
    "get_origin",
    "get_args",
    "get_forward_type",
    "resolve_annotations",
    "get_type_hints",
    "dataclass_transform",
    "ValidatorType",
    "PreFormatType",
)

logger = logging.getLogger(__name__)


ValidatorType = typing.Callable[["BaseModel", typing.Any], typing.Union[bool, None]]

PreFormatType = typing.Callable[["BaseModel", typing.Any], typing.Any]


# backward compatibility
NoneType = getattr(types, "NoneType", type(None))

COLLECTION_TYPES = frozenset(
    [
        list,
        tuple,
        set,
        frozenset,
        dict,
        collections.deque,
        collections.defaultdict,
        collections.Counter,
        collections.OrderedDict,
    ]
)


_DATACLASS_CONFIG_FIELD: typing.List[str] = [
    "init",
    "repr",
    "eq",
    "order",
    "unsafe_hash",
    "frozen",
]

_NON_DATACLASS_CONFIG_FIELD: typing.List[str] = [
    "strict_mode",
    "disable_typecheck",
    "disable_all_validation",
]

_resolved_forward_ref: typing.Dict[str, typing.Type[typing.Any]] = {}


class ModelConfigWrapper:
    init: bool = True
    repr: bool = True
    eq: bool = True
    order: bool = False
    unsafe_hash: bool = False
    frozen: bool = False

    # pydantic-mini specific config

    strict_mode: bool = False  # if true, don't coerce values

    # If true, all forward references are treated as typing.Any.
    # This, therefore, disables all validations for the field
    forward_refs_as_any: bool = False

    # If true, disable type check but apply all custom validators
    disable_typecheck: bool = False

    # If true, disable all validations
    disable_all_validation: bool = False

    def __init__(self, config: typing.Type):
        self.config = config

    def get_config(self, name: str) -> typing.Any:
        if self.config and hasattr(self.config, name):
            return getattr(self.config, name, None)
        return getattr(self.__class__, name, None)

    def get_dataclass_config(self) -> typing.Dict[str, typing.Any]:
        dt = collections.OrderedDict()
        for config_field in _DATACLASS_CONFIG_FIELD:
            dt[config_field] = self.get_config(config_field)
        return dt

    def get_non_dataclass_config(self) -> typing.Dict[str, typing.Any]:
        dt = collections.OrderedDict()
        for config_field in _NON_DATACLASS_CONFIG_FIELD:
            dt[config_field] = self.get_config(config_field)
        return dt


class Attrib:
    __slots__ = (
        "default",
        "default_factory",
        "pre_formatter",
        "required",
        "help_text",
        "allow_none",
        "gt",
        "ge",
        "lt",
        "le",
        "min_length",
        "max_length",
        "pattern",
        "_validators",
    )

    def __init__(
        self,
        default: typing.Optional[typing.Any] = MISSING,
        default_factory: typing.Optional[typing.Callable[[], typing.Any]] = MISSING,
        pre_formatter: typing.Union[PreFormatType, MISSING] = MISSING,
        required: bool = False,
        help_text: typing.Optional[str] = None,
        allow_none: bool = False,
        gt: typing.Optional[float] = None,
        ge: typing.Optional[float] = None,
        lt: typing.Optional[float] = None,
        le: typing.Optional[float] = None,
        min_length: typing.Optional[int] = None,
        max_length: typing.Optional[int] = None,
        pattern: typing.Optional[typing.Union[str, typing.Pattern]] = None,
        validators: typing.Union[typing.List[ValidatorType], MISSING] = MISSING,
    ):
        """
        Represents a data attribute with optional validation, default values, and formatting logic.

        Attributes (via __slots__):
            default (Any): A default value for the attribute, if provided.
            default_factory (Callable): A callable that generates a default value.
            pre_formatter (Callable): A function to preprocess/format the value before validation.
            required (bool): Whether the attribute is required.
            allow_none (bool): Whether None is an acceptable value.
            gt (float): Value must be greater than this (exclusive).
            ge (float): Value must be greater than or equal to this (inclusive).
            lt (float): Value must be less than this (exclusive).
            le (float): Value must be less than or equal to this (inclusive).
            min_length (int): Minimum allowed length (for iterable types like strings/lists).
            max_length (int): Maximum allowed length.
            pattern (str or Pattern): Regex pattern the value must match (typically for strings).
            _validators (List[Callable]): Custom validators to run on the value.

        Args:
            default (Any, optional): Static default value to use if none is provided.
            default_factory (Callable, optional): Function that returns a default value.
            pre_formatter (Callable, optional): Function to format/preprocess the value before validation.
            required (bool): Whether this field is required (default: False).
            allow_none (bool): Whether None is allowed as a value (default: False).
            gt, ge, lt, le (float, optional): Numeric comparison constraints.
            min_length, max_length (int, optional): Length constraints for sequences.
            pattern (str or Pattern, optional): Regex pattern constraint.
            validators (List[Callable], optional): Additional callables that validate the input.
        """
        self.default = default
        self.default_factory = default_factory
        self.pre_formatter = pre_formatter
        self.required = required
        self.allow_none = allow_none
        self.help_text = help_text
        self.gt = gt
        self.ge = ge
        self.lt = lt
        self.le = le
        self.min_length = min_length
        self.max_length = max_length
        self.pattern = pattern

        if validators is not MISSING:
            self._validators = (
                validators if isinstance(validators, (list, tuple)) else [validators]
            )
        else:
            self._validators = []

    def __repr__(self):
        return (
            "Attrib("
            f"default={self.default!r},"
            f"default_factory={self.default_factory!r},"
            ")"
        )

    def has_default(self):
        return self.default is not MISSING or self.default_factory is not MISSING

    def has_pre_formatter(self):
        return self.pre_formatter is not None and callable(self.pre_formatter)

    def _get_default(self) -> typing.Any:
        if self.default is not MISSING:
            return self.default
        elif self.default_factory is not MISSING:
            return self.default_factory()
        return MISSING

    def validate(self, value: typing.Any, field_name: str) -> typing.Optional[bool]:
        value = value or self._get_default()

        if self.allow_none and value is None:
            return True

        if self.required and value is None:
            raise ValidationError(
                f"Field '{field_name}' is required but not provided (value is None).",
                params={"field_name": field_name},
            )

        for name in ("gt", "ge", "lt", "le", "min_length", "max_length", "pattern"):
            validation_factor = getattr(self, name, None)

            # Skip the validation if 'validation_factor' is None, or if both 'value'
            # and 'self.default' are None
            if validation_factor is None or value is None:
                continue

            validator = getattr(self, f"_validate_{name}")
            validator(value)
        return True

    def execute_field_validators(self, value: typing, instance: "BaseModel") -> None:
        for validator in self._validators:
            try:
                validator(instance, value)
            except Exception as e:
                if isinstance(e, ValidationError):
                    raise
                raise ValidationError(str(e)) from e

    def _validate_gt(self, value: typing.Any):
        try:
            if not (value > self.gt):
                raise ValidationError(
                    f"Field value '{value}' is not greater than '{self.gt}'",
                    params={"gt": self.gt},
                )
        except TypeError:
            raise TypeError(
                f"Unable to apply constraint 'gt' to supplied value {value!r}"
            )

    def _validate_ge(self, value: typing.Any):
        try:
            if not (value >= self.ge):
                raise ValidationError(
                    f"Field value '{value}' is not greater than or equal to '{self.ge}'",
                    params={"ge": self.ge},
                )
        except TypeError:
            raise TypeError(
                f"Unable to apply constraint 'ge' to supplied value {value!r}"
            )

    def _validate_lt(self, value: typing.Any):
        try:
            if not (value < self.lt):
                raise ValidationError(
                    f"Field value '{value}' is not less than '{self.lt}'",
                    params={"lt": self.lt},
                )
        except TypeError:
            raise TypeError(
                f"Unable to apply constraint 'lt' to supplied value {value!r}"
            )

    def _validate_le(self, value: typing.Any):
        try:
            if not (value <= self.le):
                raise ValidationError(
                    f"Field value '{value}' is not less than or equal to '{self.le}'",
                    params={"le": self.le},
                )
        except TypeError:
            raise TypeError(
                f"Unable to apply constraint 'le' to supplied value {value!r}"
            )

    def _validate_min_length(self, value: typing.Any):
        try:
            if not (len(value) >= self.min_length):
                raise ValidationError(
                    "too_short",
                    {
                        "field_type": "Value",
                        "min_length": self.min_length,
                        "actual_length": len(value),
                    },
                )
        except TypeError:
            raise TypeError(
                f"Unable to apply constraint 'min_length' to supplied value {value!r}"
            )

    def _validate_max_length(self, value: typing.Any):
        try:
            actual_length = len(value)
            if actual_length > self.max_length:
                raise ValidationError(
                    f"Value is too long. {actual_length} > {self.max_length}",
                    {
                        "field_type": "Value",
                        "max_length": self.max_length,
                        "actual_length": actual_length,
                    },
                )
        except TypeError:
            raise TypeError(
                f"Unable to apply constraint 'max_length' to supplied value {value!r}"
            )

    def _validate_pattern(self, value: typing.Any):
        try:
            if not re.match(self.pattern, value):
                raise ValidationError(
                    f"Field value '{value}' does not match pattern",
                    params={"pattern": self.pattern, "value": value},
                )
        except TypeError:
            raise TypeError(
                f"Unable to apply constraint 'pattern' to supplied value {value!r}"
            )


if sys.version_info < (3, 9):

    def evaluate_forward_ref(type_: ForwardRef, globalns: Any, localns: Any) -> Any:
        return type_._evaluate(globalns, localns)

elif sys.version_info < (3, 12, 4):

    def evaluate_forward_ref(
        type_: ForwardRef, globalns: typing.Any, localns: typing.Any
    ) -> typing.Any:
        # Even though it is the right signature for python 3.9, mypy complains with
        # `error: Too many arguments for "_evaluate" of "ForwardRef"` hence the cast...
        # Python 3.13/3.12.4+ made `recursive_guard` a kwarg, so name it explicitly to avoid:
        # TypeError: ForwardRef._evaluate() missing 1 required keyword-only argument: 'recursive_guard'
        return typing.cast(typing.Any, type_)._evaluate(
            globalns, localns, recursive_guard=set()
        )

elif sys.version_info < (3, 14):

    def evaluate_forward_ref(
        type_: ForwardRef, globalns: typing.Any, localns: typing.Any
    ) -> typing.Any:
        # Pydantic 1.x will not support PEP 695 syntax, but provide `type_params` to avoid
        # warnings:
        return typing.cast(typing.Any, type_)._evaluate(
            globalns, localns, type_params=(), recursive_guard=set()
        )

else:

    def evaluate_forward_ref(
        type_: ForwardRef, globalns: typing.Any, localns: typing.Any
    ) -> typing.Any:
        # Pydantic 1.x will not support PEP 695 syntax, but provide `type_params` to avoid
        # warnings:
        return typing.evaluate_forward_ref(
            type_,
            globals=globalns,
            locals=localns,
            type_params=(),
            _recursive_guard=set(),
        )


def is_mini_annotated(typ) -> bool:
    origin = get_origin(typ)
    return (
        origin
        and origin is Annotated
        and hasattr(typ, "__metadata__")
        and Attrib in [inst.__class__ for inst in typ.__metadata__]
    )


def is_type(typ):
    try:
        is_typ = isinstance(typ, type)
    except TypeError:
        is_typ = False
    return is_typ


def is_initvar_type(typ):
    if hasattr(typ, "type"):
        if isinstance(typ, InitVar):
            return typ.__class__.__name__ == "InitVar"
        return hasattr(typ, "__name__") and typ.__name__ == "InitVar"
    return False


def is_class_var_type(typ) -> bool:
    return typ is typing.ClassVar or get_origin(typ) is typing.ClassVar


def is_any_type(typ) -> bool:
    """
    Check if a type annotation is typing.Any.

    Args:
        typ: A type annotation to check

    Returns:
        True if the annotation is typing.Any, False otherwise

    Examples:
        >>> is_any_type(Any)
        True
        >>> is_any_type(int)
        False
        >>> is_any_type(str)
        False
    """
    if typ is typing.Any:
        return True

    # In some Python versions, Any might be represented differently
    # Check by type name as fallback
    type_name = getattr(typ, "__name__", None)
    if type_name == "Any":
        return True

    # Check the module and qualname for edge cases
    if hasattr(typ, "__module__") and hasattr(typ, "__name__"):
        if typ.__module__ == "typing" and typ.__name__ == "Any":
            return True

    return False


def resolve_and_cache_forward_ref(
    type_: ForwardRef,
    globalns: typing.Optional[typing.Dict[str, typing.Any]] = None,
    localns: typing.Optional[typing.Dict[str, typing.Any]] = None,
    dont_resolve: bool = False,
) -> typing.Any:
    forward_ref_name = get_forward_type(type_)
    if forward_ref_name:
        if dont_resolve:
            return forward_ref_name

        _typ = _resolved_forward_ref.get(forward_ref_name)
        if _typ is None:
            try:
                _typ = evaluate_forward_ref(type_, globalns=globalns, localns=localns)
            except NameError as e:
                logger.warning("Forward reference type resolution failed: %s", e)
                raise
            _resolved_forward_ref[forward_ref_name] = _typ

        return _typ
    return None


def get_type(
    typ: typing.Any,
    globalns: typing.Optional[typing.Dict[str, typing.Any]] = None,
    localns: typing.Optional[typing.Dict[str, typing.Any]] = None,
    resolve_forward_ref: bool = True,
) -> typing.Any:
    if is_type(typ):
        return typ

    if is_optional_type(typ):
        type_args = get_args(typ)
        if type_args:
            return get_type(
                type_args[0],
                resolve_forward_ref=resolve_forward_ref,
                globalns=globalns,
                localns=localns,
            )
        else:
            return NoneType

    if is_any_type(typ):
        return object

    origin = get_origin(typ)
    if is_type(origin):
        return origin

    forward_ref_type = resolve_and_cache_forward_ref(
        typ, globalns=globalns, localns=localns, dont_resolve=not resolve_forward_ref
    )
    if forward_ref_type is not None:
        return forward_ref_type

    type_args = get_args(typ)
    if len(type_args) > 0:
        return get_type(type_args[0], globalns=globalns, localns=localns)
    else:
        return None


def get_type_hints(
    typ: typing.Any,
    globalns: typing.Optional[typing.Dict[str, typing.Any]] = None,
    localns: typing.Optional[typing.Dict[str, typing.Any]] = None,
    include_extras: bool = False,
) -> typing.Dict[str, typing.Any]:
    if sys.version_info < (3, 9):
        return typing.get_type_hints(typ, globalns, localns)
    else:
        return typing.get_type_hints(
            typ, globalns, localns, include_extras=include_extras
        )


def get_mini_annotation_hints(cls, global_ns=None, local_ns=None):
    try:
        hints = get_type_hints(
            cls, globalns=global_ns, localns=local_ns, include_extras=True
        )

        if sys.version_info >= (3, 14):
            # Check if 3.14 stripped our MiniAnnotated/Annotated wrapper
            # If hints contain 'str' instead of 'Annotated[str, ...]', we must fall back
            first_hint = next(iter(hints.values()), None)
            if first_hint and typing.get_origin(first_hint) is not typing.Annotated:
                return inspect.get_annotations(cls, eval_str=True)

        return hints
    except (TypeError, NameError):
        return getattr(cls, "__annotations__", {})


def resolve_annotations(
    cls: type, global_ns: typing.Any = None, local_ns: typing.Any = None
) -> typing.Dict[str, typing.Any]:

    return get_mini_annotation_hints(cls, global_ns=global_ns, local_ns=local_ns)


def is_optional_type(typ):
    if hasattr(typ, "__origin__") and typ.__origin__ is typing.Union:
        return NoneType in typ.__args__
    elif typ is typing.Optional:
        return True
    return False


def is_collection(typ) -> typing.Tuple[bool, typing.Optional[type]]:
    origin = get_origin(typ)
    if origin and origin in COLLECTION_TYPES:
        return True, origin
    return False, None


def get_forward_type(typ):
    """
    Determine if a type annotation is a forward reference and extract the type.

    Args:
        typ: A type annotation that may be a forward reference

    Returns:
        The string name of the forward reference if it is one, otherwise None
    """
    # Check if it's already a string
    if isinstance(typ, str):
        return typ

    # Check if it's a ForwardRef object (Python 3.7+)
    if isinstance(typ, ForwardRef):
        # In Python 3.7-3.10, use __forward_arg__
        # In Python 3.11+, use __arg__
        if sys.version_info >= (3, 11):
            try:
                return typ.__arg__
            except AttributeError:
                return getattr(typ, "__forward_arg__", typing.Any)
        else:
            return typ.__forward_arg__

    # Check if it's a generic type with forward references (e.g., List['MyClass'])
    origin = get_origin(typ)
    if origin is not None:
        args = get_args(typ)
        # Return the first forward reference found in generic args
        for arg in args:
            forward = get_forward_type(arg)
            if forward:
                return forward

    return None


def is_builtin_type(typ):
    typ = typ if isinstance(typ, type) else type(typ)
    return typ.__module__ in ("builtins", "__builtins__")


class MiniAnnotated:
    __slots__ = ()

    def __init_subclass__(cls, **kwargs):
        raise TypeError(f"Cannot subclass {cls.__module__}.MiniAnnotated")

    def __new__(cls, *args, **kwargs):
        raise TypeError("Type MiniAnnotated cannot be instantiated.")

    @typing._tp_cache
    def __class_getitem__(cls, params):
        if not isinstance(params, tuple):
            params = (params, Attrib())

        if len(params) != 2:
            raise TypeError(
                "MiniAnnotated[...] should be used with exactly two arguments (a type and an Attrib)."
            )

        typ = params[0]

        actual_typ = get_type(typ, resolve_forward_ref=False)
        forward_typ = get_forward_type(typ)
        if actual_typ is None and forward_typ is None:
            raise ValueError("'{}' is not a type".format(params[0]))

        query = params[1]
        if not isinstance(query, Attrib):
            raise TypeError("Parameter '{}' must be instance of Attrib".format(1))
        return Annotated[typ, query]
