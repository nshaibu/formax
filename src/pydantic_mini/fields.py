import typing
import inspect
from enum import Enum
from functools import lru_cache
from dataclasses import fields, Field, field, MISSING, is_dataclass
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
    evaluate_forward_ref,
    ValidatorType,
    PreFormatType,
    resolve_and_cache_forward_ref,
)
from .utils import init_class
from .exceptions import ValidationError

if typing.TYPE_CHECKING:
    from .base import BaseModel


# _resolved_forward_ref: typing.Dict[str, typing.Type[typing.Any]] = {}


class MiniField:

    __slots__ = (
        "name",
        "private_name",
        "expected_type",
        "_field_validators",
        "_preformat_callbacks",
        "_mini_annotated_type",
        "_actual_annotated_type",
        "_inner_type_args",
        "_query",
        "type_annotation_args",
        "is_builtin",
        "is_enum",
        "is_model",
        "is_collection",
        "is_class",
        "_is_type_expectation_init",
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

        self.is_collection, self.expected_type = is_collection(
            self._actual_annotated_type
        )

        self._is_type_expectation_init: bool = False

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

    def _init_type_expectations(self, instance: "BaseModel"):
        self.type_annotation_args: typing.Optional[typing.Tuple[typing.Any]] = (
            self.type_can_be_validated(
                self._actual_annotated_type, instance=instance, resolve_forward_ref=True
            )
        )

        if not self.is_collection:
            self.expected_type = (
                self.type_annotation_args[0]
                if self.type_annotation_args
                else typing.Any
            )

        self.is_builtin: bool = is_builtin_type(self.expected_type)
        self.is_enum: bool = isinstance(self.expected_type, type) and issubclass(
            self.expected_type, Enum
        )
        self.is_model: bool = hasattr(
            self.expected_type, "__pydantic_mini_extra_config__"
        ) or is_dataclass(self.expected_type)
        self.is_class: bool = inspect.isclass(self.expected_type)

        self._is_type_expectation_init = True

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

        # self.type_annotation_args = [self.resolve_actual_type(typ_) for typ_ in self.type_annotation_args]
        print(self.type_annotation_args)

        if not self._is_type_expectation_init:
            self._init_type_expectations(instance)

        if isinstance(value, MiniField):
            value = value.get_default()
            if value is MISSING:
                raise AttributeError("Field required")

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
                    coerced_value = self._value_coerce(value, instance)
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

    def _value_coerce(self, value: typing.Any, instance: "BaseModel") -> typing.Any:
        from .base import BaseModel

        if self.is_collection:
            if self.type_annotation_args and isinstance(value, (dict, list)):
                value = value if isinstance(value, list) else [value]
                inner_type: type = self._inner_type_args[0]

                inner_type = self.resolve_actual_type(
                    inner_type, globalns=self.get_model_context(instance)
                )

                if is_builtin_type(inner_type):
                    return self.expected_type([inner_type(val) for val in value])
                elif (
                    (isinstance(inner_type, type) and issubclass(inner_type, BaseModel))
                    or is_dataclass(inner_type)
                    or inspect.isclass(inner_type)
                ):
                    return self.expected_type(
                        [
                            (
                                init_class(inner_type, val)
                                if isinstance(val, dict)
                                else val
                            )
                            for val in value
                        ]
                    )
        elif self._actual_annotated_type:
            if isinstance(value, dict):
                if self.is_model or self.is_class:
                    return init_class(self.expected_type, value)

            # Enums (Coerce string/int to Enum member)
            elif self.is_enum:
                if value is not None and not isinstance(value, self.expected_type):
                    try:
                        return self.expected_type(value)
                    except ValueError:
                        pass
            # Primitives (Last-ditch coercion for strings to int/float)
            elif self.is_builtin:
                if value is not None and not isinstance(value, self.expected_type):
                    try:
                        return self.expected_type(value)
                    except (ValueError, TypeError):
                        pass

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
            elif not isinstance(value, self.type_annotation_args):
                raise TypeError(
                    f"Field '{self.name!r}' should be of type {self.type_annotation_args}, "
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
            # _typ = _resolved_forward_ref.get(self.forward_ref_type_name)
            # if _typ is None:
            #     _typ = evaluate_forward_ref(typ, globalns=globals(), localns=locals())
            #     _resolved_forward_ref[self.forward_ref_type_name] = _typ
            return resolve_and_cache_forward_ref(
                typ, globalns=globalns, localns=localns
            )
        return typ

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
                # return tuple([get_type(_typ) for _typ in type_args if _typ is not None])
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
