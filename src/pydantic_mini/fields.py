import typing
import inspect
from enum import Enum
from dataclasses import fields as dc_fields, Field, MISSING, is_dataclass
from .typing import (
    is_mini_annotated,
    get_type,
    get_origin,
    get_args,
    get_forward_type,
    Annotated,
    Attrib,
    is_collection,
    is_optional_type,
    is_builtin_type,
    ValidatorType,
    PreFormatType,
    resolve_and_cache_forward_ref,
)
from .exceptions import ValidationError

if typing.TYPE_CHECKING:
    from .base import BaseModel


class _ExpectedType:
    __slots__ = ("type", "order", "is_builtin", "is_enum", "is_model", "is_class")

    def __init__(self, typ_: typing.Type[typing.Any], order: int):
        self.type: type = typ_

        # will be saved in non-ordered datastructures so we keep the order
        self.order = order

        self.is_builtin: bool = is_builtin_type(self.type)
        self.is_enum: bool = isinstance(self.type, type) and issubclass(self.type, Enum)
        self.is_model: bool = hasattr(
            self.type, "__pydantic_mini_extra_config__"
        ) or is_dataclass(self.type)
        self.is_class: bool = inspect.isclass(self.type)

    def isinstance_of(self, value: typing.Any) -> bool:
        return isinstance(value, self.type)

    def __str__(self) -> str:
        return self.type.__name__

    def __repr__(self) -> str:
        return repr(self.type)

    def __call__(self, *args, **kwargs):
        try:
            return self.type(*args, **kwargs)
        except TypeError as e:
            raise TypeError(f"Failed to instantiate {str(self.type)} from dict: {e}")

    def __hash__(self) -> int:
        return hash(
            (self.type, self.is_builtin, self.is_enum, self.is_model, self.is_class)
        )


class _ExpectedTypeResolver:
    __slots__ = ("_actual_types", "_strict_model")

    def __init__(
        self, actual_types: typing.Tuple[type], strict_model: bool = False
    ) -> None:
        """
        Validate and coerce datatype
        :param actual_types: Tuple of types to validate
        :param strict_model: Validation model
        """
        if not actual_types:
            raise TypeError("No types were provided")

        self._actual_types: typing.List[_ExpectedType] = []

        for index, typ in enumerate(actual_types):
            expected_type = _ExpectedType(typ, order=index)
            if expected_type not in self._actual_types:
                self._actual_types.append(expected_type)

        self._actual_types = sorted(self._actual_types, key=lambda t: t.order)

        self._strict_model: bool = strict_model

    def type_string(self) -> str:
        if self._actual_types:
            return ", ".join([str(t) for t in self._actual_types])  # type: ignore
        return ""

    def validate(self, value: typing.Any) -> bool:
        """Check if value matches any of the expected types"""
        # import pdb;pdb.set_trace()
        return self.get_matching_type(value) is not None

    def coerce(self, value: typing.Any) -> typing.Any:
        """Convert value to one of the expected types"""
        matching_type = self.get_matching_type(value)

        if matching_type is None:
            raise TypeError(
                f"Cannot coerce {type(value).__name__} to any of {self.type_string()}"
            )

        if matching_type.isinstance_of(value):
            return value

        if isinstance(value, dict):
            if matching_type.is_model or matching_type.is_class:
                return self._instantiate_from_dict(matching_type, value)

        try:
            return matching_type(value)
        except (ValueError, TypeError) as e:
            raise TypeError(
                f"Failed to coerce {value} to {matching_type.__name__}: {e}"
            )

    def get_matching_type(self, value: typing.Any) -> typing.Optional[_ExpectedType]:
        """Determine which type best matches the value"""

        for expected_type in self._actual_types:
            if expected_type.isinstance_of(value):
                return expected_type

        # coercion type detection section
        if not self._strict_model:
            if isinstance(value, dict):
                for expected_type in self._actual_types:
                    if expected_type.is_class and self._matches_class_signature(
                        expected_type, value
                    ):
                        return expected_type

            for expected_type in self._actual_types:
                if expected_type.is_builtin or expected_type.is_enum:
                    try:
                        expected_type(value)
                        return expected_type
                    except (ValueError, TypeError):
                        continue

        return None

    def _matches_class_signature(
        self, expected_type: _ExpectedType, data: dict
    ) -> bool:
        """Check if dict keys match class constructor signature."""
        try:
            if expected_type.is_model:
                fields = dc_fields(expected_type.type)  # type: ignore
                field_names = {f.name for f in fields}
                required = {
                    f.name
                    for f in fields
                    if f.default == MISSING and f.default_factory == MISSING
                }
                # Dataclasses don't support **kwargs in the standard sense unless
                # custom __init__ is defined, so we stick to field names.
                return required.issubset(data.keys()) and set(data.keys()).issubset(
                    field_names
                )

            else:
                sig = inspect.signature(expected_type.type)
                params = sig.parameters

                # Check for **kwargs
                has_kwargs = any(p.kind == p.VAR_KEYWORD for p in params.values())

                field_names = set(params.keys())
                required = {
                    n
                    for n, p in params.items()
                    if p.default == inspect.Parameter.empty
                    and p.kind not in (p.VAR_KEYWORD, p.VAR_POSITIONAL)
                }

                # All required parameters MUST be in the dict.
                if not required.issubset(data.keys()):
                    return False

                # If the class DOES NOT have **kwargs, keys must be a subset of field names.
                # If the class DOES have **kwargs, any extra keys are allowed.
                if not has_kwargs and not set(data.keys()).issubset(field_names):
                    return False

                return True

        except (ValueError, TypeError):
            return False

    def _instantiate_from_dict(
        self, _expected_type: _ExpectedType, data: typing.Dict[str, typing.Any]
    ) -> typing.Any:
        """Instantiate a class from a dictionary"""
        return _expected_type(**data)


class MiniField:

    __slots__ = (
        "name",
        "private_name",
        "expected_type",
        "inner_type",
        "_field_validators",
        "_preformat_callbacks",
        "_mini_annotated_type",
        "_actual_annotated_type",
        "_inner_type_args",
        "_query",
        "type_annotation_args",
        "is_collection",
        "forward_ref_type_name",
        "_default",
        "_default_factory",
    )

    def __init__(
        self,
        name: str,
        mini_annotated: Annotated,
        dc_field_obj: typing.Optional[Field] = None,
    ):
        if not is_mini_annotated(mini_annotated):
            raise ValidationError(
                "Field '{}' should be annotated with 'MiniAnnotated'.".format(name),
                params={"field": name, "annotation": mini_annotated},
            )
        self.name = name
        self.private_name = f"_{name}"

        # type decomposition
        self._mini_annotated_type = mini_annotated
        self._actual_annotated_type = mini_annotated.__args__[0]
        self._query: Attrib = mini_annotated.__metadata__[0]
        self.type_annotation_args: typing.Optional[typing.Tuple[typing.Any]] = (
            self.type_can_be_validated(
                self._actual_annotated_type, resolve_forward_ref=False
            )
        )

        self._inner_type_args = get_args(self._actual_annotated_type)

        self.is_collection, _ = is_collection(self._actual_annotated_type)

        self.expected_type: typing.Optional[_ExpectedTypeResolver] = None
        self.inner_type: typing.Optional[typing.Type[typing.Any]] = None

        self.forward_ref_type_name: typing.Optional[str] = get_forward_type(
            self._actual_annotated_type
        )

        self._field_validators: typing.Set[ValidatorType] = set()
        self._preformat_callbacks: typing.Set[PreFormatType] = set()

        if self._query.pre_formatter is not MISSING:
            if callable(self._query.pre_formatter):
                self._preformat_callbacks.add(self._query.pre_formatter)

        for func in self._query._validators:
            if callable(func):
                self._field_validators.add(func)

        # Mirror dataclass Field internal state
        self._default = (
            self._query.default
            if self._query.default is MISSING
            else dc_field_obj.default
        )
        self._default_factory = (
            self._query.default_factory
            if self._query.default_factory is MISSING
            else dc_field_obj.default_factory
        )

    def get_default(self) -> typing.Any:
        if self._default is not MISSING:
            return self._default
        elif self._default_factory is not MISSING:
            return self._default_factory()
        return MISSING

    def _init_type_expectations(self, instance: "BaseModel", strict_status: bool):
        self.type_annotation_args: typing.Optional[typing.Tuple[typing.Any]] = (
            self.type_can_be_validated(
                self._actual_annotated_type, instance=instance, resolve_forward_ref=True
            )
        )

        self.expected_type = _ExpectedTypeResolver(
            actual_types=self.type_annotation_args, strict_model=strict_status
        )

        inner_types_list: typing.List[type] = []

        for t in self._inner_type_args:
            if t not in inner_types_list:
                typ = get_type(t, globalns=self.get_model_context(instance))
                if typ is not None:
                    inner_types_list.append(typ)

        try:
            self.inner_type = _ExpectedTypeResolver(actual_types=tuple(inner_types_list), strict_model=strict_status)  # type: ignore
        except TypeError:
            self.inner_type = None

    def __get__(self, instance: "BaseModel", owner: typing.Any = None) -> typing.Any:
        if instance is None:
            return self

        value = instance.__dict__.get(self.private_name, self.get_default())

        if value is MISSING:
            raise AttributeError(
                f"'{owner.__name__}' object has no attribute '{self.name}'"
            )

        # Cache the default back to the instance
        instance.__dict__[self.private_name] = value

        return value

    def __set__(self, instance: "BaseModel", value: typing.Any) -> None:
        config = self.get_model_config(instance)
        strict_mode = config.get("strict_mode", False)
        disable_typecheck = config.get("disable_typecheck", False)
        disable_all_validation = config.get("disable_all_validation", False)

        if self.expected_type is None:
            self._init_type_expectations(instance, strict_status=strict_mode)

        if isinstance(value, MiniField):
            value = value.get_default()
            if value is MISSING:
                raise AttributeError(
                    "No value provided for field '{}'".format(self.name)
                )

        for preformat_callback in self._preformat_callbacks:
            try:
                if callable(preformat_callback):
                    value = preformat_callback(instance, value)
            except Exception as e:
                raise RuntimeError(
                    f"Preprocessor '{preformat_callback.__name__}' failed to process value '{value}'"
                ) from e

        if not disable_all_validation:
            # no type validation for Any field type and type checking is not disabled
            if self._actual_annotated_type is not typing.Any and not disable_typecheck:
                if not strict_mode:
                    coerced_value = self._value_coerce(value)
                    if coerced_value is not None:
                        value = coerced_value
                self._field_type_validator(value, instance)
            else:
                # run other field validators when type checking is disabled
                if self._query:
                    self._query.execute_field_validators(value, instance)
                    self._query.validate(value, self.name)

            try:
                for validator in self._field_validators:
                    status = validator(instance, value)
                    if status is False:
                        raise ValidationError(
                            "Validation of field '{}' with value '{}' failed.".format(
                                self.name, value
                            )
                        )
            except Exception as e:
                if isinstance(e, ValidationError):
                    raise
                raise ValidationError("Validation error") from e

        instance.__dict__[self.private_name] = value

    @staticmethod
    def get_model_config(instance: "BaseModel") -> typing.Dict[str, typing.Any]:
        return getattr(instance, "__pydantic_mini_extra_config__", {})

    @staticmethod
    def get_model_context(
        instance: "BaseModel",
    ) -> typing.Optional[typing.Dict[str, typing.Any]]:
        if instance is None:
            return None
        return getattr(inspect.getmodule(instance.__class__), "__dict__", None)

    def _value_coerce(self, value: typing.Any) -> typing.Any:
        if self.is_collection:
            if self.type_annotation_args and isinstance(value, (dict, list)):
                value = value if isinstance(value, list) else [value]
                if self.inner_type is not None:
                    return self.expected_type.coerce(
                        [self.inner_type.coerce(val) for val in value]
                    )
        else:
            return self.expected_type.coerce(value)

        return None

    def _field_type_validator(self, value: typing.Any, instance: "BaseModel") -> None:
        if not self._query.has_default() and value is None:
            raise ValidationError(
                "Field '{}' cannot be empty.".format(self.name),
                params={"field": self.name, "annotation": self._mini_annotated_type},
            )

        self._query.execute_field_validators(value, instance)

        if self._actual_annotated_type and typing.Any not in self.type_annotation_args:
            if self.is_collection:
                inner_type: type = self._inner_type_args[0]
                if inner_type and inner_type is not typing.Any:
                    inner_type = self.resolve_actual_type(
                        inner_type, globalns=self.get_model_context(instance)
                    )

                    if any([not isinstance(val, inner_type) for val in value]):
                        raise TypeError(
                            "Expected a collection of values of type '{}'. Values: {} ".format(
                                inner_type, value
                            )
                        )
            elif not self.expected_type.validate(
                value
            ):  # not isinstance(value, self.type_annotation_args):
                raise TypeError(
                    f"Field '{self.name!r}' should be of type {self.expected_type.type_string()}, "
                    f"but got {type(value).__name__}."
                )

        self._query.validate(value, self.name)

    def resolve_actual_type(
        self,
        typ: typing.Type[typing.Any],
        globalns: typing.Dict[str, typing.Any],
        localns: typing.Optional[typing.Dict[str, typing.Any]] = None,
    ) -> typing.Type[typing.Any]:
        if self.forward_ref_type_name:
            typ = typing.cast(typing.ForwardRef, typ)
            typ_temp = resolve_and_cache_forward_ref(
                typ, globalns=globalns, localns=localns
            )
            if typ_temp is None:
                return get_type(typ, globalns=globalns, localns=localns)
            return typ_temp
        return get_type(typ, globalns=globalns, localns=localns)

    def type_can_be_validated(
        self,
        typ,
        instance: typing.Optional["BaseModel"] = None,
        resolve_forward_ref: bool = True,
    ) -> typing.Optional[typing.Tuple]:
        origin = get_origin(typ)
        if origin is typing.Union:
            type_args = get_args(typ)
            if type_args:
                _set = set()
                for arg in type_args:
                    _arg_type = get_type(
                        arg,
                        globalns=self.get_model_context(instance),
                        resolve_forward_ref=resolve_forward_ref,
                    )
                    if _arg_type is not None:
                        _set.add(_arg_type)

                return tuple(_set)
        else:
            return (
                get_type(
                    typ,
                    globalns=self.get_model_context(instance),
                    resolve_forward_ref=resolve_forward_ref,
                ),
            )

        return None

    def has_validator(self, func: ValidatorType) -> bool:
        return func in self._field_validators

    def has_preformat_callback(self, func: PreFormatType) -> bool:
        return func in self._preformat_callbacks

    def add_validator(self, func: ValidatorType) -> None:
        if not callable(func):
            raise TypeError("Validator '{}' is not callable.".format(func))
        self._field_validators.add(func)

    def add_preformat_callback(self, func: PreFormatType) -> None:
        if not callable(func):
            raise TypeError("PreFormat callback '{}' is not callable.".format(func))
        self._preformat_callbacks.add(func)

    def set_field_value(self, instance: "BaseModel", value) -> None:
        instance.__dict__[self.private_name] = value
