from __future__ import annotations
import re
import logging
import sys
import types
import typing
import inspect
import warnings
import collections
from enum import IntFlag, Enum, auto
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
from .utils import process_validator_errors

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
    "ValidationFlags",
    "InitStrategy",
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


class InitStrategy(Enum):
    DATACLASS = auto()  # default dataclass __init__
    FAST = auto()  # codegen __init__ (batch assignment)
    CUSTOM = auto()  # user-defined __init__


class ValidationFlags(IntFlag):
    """Bitwise flags for validation control."""

    # Core validation components
    TYPECHECK = 1 << 0  # 0b001 = 1 - Type checking (isinstance)
    COERCE = 1 << 1  # 0b010 = 2  - Type coercion ("123" → 123)

    # Convenience combinations
    NONE = 0  # No validation at all
    STRICT = TYPECHECK  # No coercion, but validate
    VALIDATED = TYPECHECK | COERCE  # Full validation (default)

    @staticmethod
    def should_typecheck(flags: "ValidationFlags") -> bool:
        """Check if type checking is enabled."""
        return (flags & ValidationFlags.TYPECHECK) != 0

    @staticmethod
    def should_coerce(flags: "ValidationFlags") -> bool:
        """Check if type coercion is enabled."""
        return (flags & ValidationFlags.COERCE) != 0

    @staticmethod
    def is_validated(flags: "ValidationFlags") -> bool:
        """Check if full validation is enabled (typecheck + coerce)."""
        required = ValidationFlags.TYPECHECK | ValidationFlags.COERCE
        return (flags & required) == required


class ModelConfigWrapper:
    """
    Wrapper for model configuration options.

    Provides defaults and validation for both standard dataclass
    config and pydantic-mini specific options.
    """

    # Standard dataclass config
    DEFAULT_REPR = True
    DEFAULT_EQ = True
    DEFAULT_ORDER = False
    DEFAULT_UNSAFE_HASH = False
    DEFAULT_FROZEN = False

    # Pydantic-mini specific
    DEFAULT_INIT_STRATEGY = InitStrategy.FAST
    DEFAULT_VALIDATION = ValidationFlags.VALIDATED
    DEFAULT_FORWARD_REFS_AS_ANY = False
    DEFAULT_SCHEMA_MODE = False

    DEFAULT_DROP_INHERITED_VALIDATORS = False
    DEFAULT_DROP_INHERITED_PREFORMATTERS = False

    DEFAULT_UNSAFE_DISABLE_VALIDATORS = False
    DEFAULT_UNSAFE_DISABLE_PREFORMATTERS = False

    def __init__(self, config: typing.Optional[typing.Type[typing.Any]] = None):
        # Standard dataclass config
        self.repr: bool = self.DEFAULT_REPR
        self.eq: bool = self.DEFAULT_EQ
        self.order: bool = self.DEFAULT_ORDER
        self.unsafe_hash: bool = self.DEFAULT_UNSAFE_HASH
        self.frozen: bool = self.DEFAULT_FROZEN

        # Init strategy
        self.init_strategy: InitStrategy = self.DEFAULT_INIT_STRATEGY

        # Validation control
        self.validation: ValidationFlags = self.DEFAULT_VALIDATION

        # Other options,
        # If true, all forward references are treated as typing.Any.
        # This, therefore, disables all validations for the field
        self.forward_refs_as_any: bool = self.DEFAULT_FORWARD_REFS_AS_ANY

        self.schema_mode: bool = self.DEFAULT_SCHEMA_MODE

        self.drop_inherited_validators = self.DEFAULT_DROP_INHERITED_VALIDATORS
        self.drop_inherited_preformatters = self.DEFAULT_DROP_INHERITED_PREFORMATTERS

        self.skip_validators = self.DEFAULT_UNSAFE_DISABLE_VALIDATORS
        self.skip_preformatters = self.DEFAULT_UNSAFE_DISABLE_PREFORMATTERS

        self._config = config

        if config is not None:
            self._apply_config(config)
            self._validate_config()

    def _apply_config(self, config: typing.Type[typing.Any]) -> None:
        for key, value in config.__dict__.items():
            if key.startswith("_") or callable(value):
                continue

            if hasattr(self, key):
                self.__dict__[key] = value
            else:
                warnings.warn(
                    f"Unknown configuration option: {key}", UserWarning, stacklevel=3
                )

    def _validate_config(self) -> None:
        # Validate frozen + eq combination
        if self.frozen and not self.eq:
            warnings.warn(
                "frozen=True with eq=False may cause issues with hashing",
                UserWarning,
                stacklevel=3,
            )

    def should_typecheck(self) -> bool:
        """Check if type checking is enabled."""
        return ValidationFlags.should_typecheck(self.validation)

    def should_coerce(self) -> bool:
        """Check if type coercion is enabled."""
        return ValidationFlags.should_coerce(self.validation)

    def is_validated(self) -> bool:
        """Check if full validation is enabled."""
        return ValidationFlags.is_validated(self.validation)

    def as_dataclass_kwargs(self) -> dict:
        return {
            "init": True,
            "repr": self.repr,
            "eq": self.eq,
            "order": self.order,
            "unsafe_hash": self.unsafe_hash,
            "frozen": self.frozen,
        }

    def __repr__(self) -> str:
        return (
            f"ModelConfigWrapper("
            f"init_strategy={self.init_strategy.value}, "
            f"frozen={self.frozen})"
        )

    def copy(self, **overrides) -> "ModelConfigWrapper":
        """
        Create a copy of config with optional overrides.

        Args:
            **overrides: Configuration values to override.

        Returns:
            New ModelConfigWrapper instance.

        Example:
            >>> config = ModelConfigWrapper()
            >>> strict_config = config.copy(validation=ValidationFlags.STRICT)
        """
        new_config = ModelConfigWrapper(self._config)

        for key, value in overrides.items():
            if hasattr(new_config, key):
                setattr(new_config, key, value)
            else:
                raise ValueError(f"Unknown config option: {key}")

        new_config._validate_config()

        return new_config


class Attrib:
    __slots__ = (
        "field_name",
        "default",
        "default_factory",
        "pre_formatter",
        "help_text",
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
        help_text: typing.Optional[str] = None,
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
            gt, ge, lt, le (float, optional): Numeric comparison constraints.
            min_length, max_length (int, optional): Length constraints for sequences.
            pattern (str or Pattern, optional): Regex pattern constraint.
            validators (List[Callable], optional): Additional callables that validate the input.
        """
        self.field_name: typing.Optional[str] = None
        self.default = default
        self.default_factory = default_factory
        self.pre_formatter = pre_formatter
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

    @property
    def validators(self) -> typing.List[ValidatorType]:
        return self._validators

    def has_default(self):
        return self.default is not MISSING or self.default_factory is not MISSING

    def has_pre_formatter(self):
        return self.pre_formatter is not None and callable(self.pre_formatter)

    def has_validators(self):
        return len(self._validators) > 0

    def validate(
        self,
        instance: "BaseModel",
        value: typing.Any,
        field_name: str,
        aggregate_errors: bool,
    ) -> typing.Optional[bool]:

        self.field_name = field_name

        for name in ("gt", "ge", "lt", "le", "min_length", "max_length", "pattern"):
            validation_factor = getattr(self, name, None)

            # Skip the validation if 'validation_factor' is None, or if both 'value'
            # and 'self.default' are None
            if validation_factor is None or value is None:
                continue

            validator = getattr(self, f"_validate_{name}")
            try:
                validator(value)
            except Exception as e:
                err = process_validator_errors(
                    instance=instance,
                    field_name=field_name,
                    value=value,
                    error=e,
                    aggregate_errors=aggregate_errors,
                )
                if err:
                    raise err
        return True

    def _validate_gt(self, value: typing.Any):
        params = {
            "validator": "greater_than",
            "comparison_operator": "gt",
            "comparison_value": self.gt,
        }
        try:
            if not (value > self.gt):
                raise ValidationError(
                    f"Field value '{value}' is not greater than '{self.gt}'",
                    field=self.field_name,
                    value=value,
                    params=params,
                )
        except TypeError as e:
            raise ValidationError(
                f"Unable to apply constraint 'gt' to supplied value {value!r}",
                field=self.field_name,
                value=value,
                params={"comparison_error": str(e), **params},
            )

    def _validate_ge(self, value: typing.Any):
        params = {
            "validator": "greater_than_or_equals_to",
            "comparison_operator": "ge",
            "comparison_value": self.ge,
        }
        try:
            if not (value >= self.ge):
                raise ValidationError(
                    f"Field value '{value}' is not greater than or equal to '{self.ge}'",
                    field=self.field_name,
                    value=value,
                    params=params,
                )
        except TypeError as e:
            raise ValidationError(
                f"Unable to apply constraint 'ge' to supplied value {value!r}",
                field=self.field_name,
                value=value,
                params={**params, "comparison_error": str(e)},
            )

    def _validate_lt(self, value: typing.Any):
        params = {
            "validator": "less_than",
            "comparison_operator": "lt",
            "comparison_value": self.lt,
        }

        try:
            if not (value < self.lt):
                raise ValidationError(
                    f"Field value '{value}' is not less than '{self.lt}'",
                    field=self.field_name,
                    value=value,
                    params=params,
                )
        except TypeError as e:
            raise ValidationError(
                f"Unable to apply constraint 'lt' to supplied value {value!r}",
                field=self.field_name,
                value=value,
                params={**params, "comparison_error": str(e)},
            )

    def _validate_le(self, value: typing.Any):
        params = {
            "validator": "less_than_or_equals_to",
            "comparison_operator": "le",
            "comparison_value": self.le,
        }

        try:
            if not (value <= self.le):
                raise ValidationError(
                    f"Field value '{value}' is not less than or equal to '{self.le}'",
                    field=self.field_name,
                    value=value,
                    params=params,
                )
        except TypeError as e:
            raise ValidationError(
                f"Unable to apply constraint 'le' to supplied value {value!r}",
                field=self.field_name,
                value=value,
                params={**params, "comparison_error": str(e)},
            )

    def _validate_min_length(self, value: typing.Any):
        try:
            if not (len(value) >= self.min_length):
                raise ValidationError(
                    f"Field value '{value}' is too short, must be at least {self.min_length} characters",
                    field=self.field_name,
                    value=value,
                    params={
                        "validator": "too_short",
                        "min_length": self.min_length,
                    },
                )
        except TypeError:
            raise ValidationError(
                f"Unable to apply constraint 'min_length' to supplied value {value!r}",
                field=self.field_name,
                value=value,
                params={"validator": "too_short", "min_length": self.min_length},
            )

    def _validate_max_length(self, value: typing.Any):
        try:
            actual_length = len(value)
            if actual_length > self.max_length:
                raise ValidationError(
                    f"Field value {value!r} is too long. {actual_length} > {self.max_length}",
                    field=self.field_name,
                    value=value,
                    params={
                        "validator": "too_long",
                        "max_length": self.max_length,
                        "actual_length": actual_length,
                    },
                )
        except TypeError:
            raise ValidationError(
                f"Unable to apply constraint 'max_length' to supplied value {value!r}",
                field=self.field_name,
                value=value,
                params={"validator": "too_long", "max_length": self.max_length},
            )

    def _validate_pattern(self, value: typing.Any):
        params = {"pattern": self.pattern, "validator": "pattern", "value": value}
        try:
            if not re.match(self.pattern, value):
                raise ValidationError(
                    f"Field value '{value}' does not match pattern",
                    field=self.field_name,
                    value=value,
                    params=params,
                )
        except TypeError:
            raise ValidationError(
                f"Unable to apply constraint 'pattern' to supplied value {value!r}",
                field=self.field_name,
                value=value,
                params=params,
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
