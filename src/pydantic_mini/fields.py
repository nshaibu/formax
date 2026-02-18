import typing
import inspect
from enum import Enum
from dataclasses import fields as dc_fields, Field, MISSING, is_dataclass
from typing import ForwardRef
from .typing import (
    is_mini_annotated,
    get_type,
    get_origin,
    get_args,
    get_forward_type,
    Annotated,
    Attrib,
    NoneType,
    is_collection,
    is_builtin_type,
    is_any_type,
    ValidatorType,
    PreFormatType,
    resolve_and_cache_forward_ref,
    ModelConfigWrapper,
    ValidationFlags,
)
from .exceptions import ValidationError
from .utils import (
    make_private_field,
    process_validator_errors,
    PYDANTIC_MINI_MODEL_CONFIG,
    PYDANTIC_MINI_SIGNATURE_MATCHER,
    PYDANTIC_MINI_MODEL_CONTEXT,
)

if typing.TYPE_CHECKING:
    from .base import BaseModel


class _ClassSignatureMatcher:
    __slots__ = ("required", "allowed", "has_kwargs")

    def __init__(self, cls):
        try:
            if is_builtin_type(cls) or issubclass(cls, Enum) or cls is typing.Any:
                self._no_sig()
            elif is_dataclass(cls):
                fields = dc_fields(cls)
                self.allowed = frozenset([f.name for f in fields])
                self.required = frozenset(
                    [
                        f.name
                        for f in fields
                        if f.default == MISSING and f.default_factory == MISSING
                    ]
                )
                self.has_kwargs = False

            else:
                sig = inspect.signature(cls)
                params = sig.parameters
                self.allowed = frozenset(params.keys())
                self.required = frozenset(
                    [
                        name
                        for name, p in params.items()
                        if p.default == inspect.Parameter.empty
                        and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
                    ]
                )
                self.has_kwargs = any(p.kind == p.VAR_KEYWORD for p in params.values())
        except (TypeError, ValueError):
            self._no_sig()

    def _no_sig(self):
        self.required = frozenset()
        self.allowed = frozenset()
        self.has_kwargs = False

    def __bool__(self) -> bool:
        return bool(self.required) or bool(self.allowed)


_BUILTIN_TYPES = frozenset(
    {
        int,
        float,
        str,
        bool,
        bytes,
        bytearray,
        list,
        dict,
        set,
        tuple,
        frozenset,
        complex,
        range,
        memoryview,
        NoneType,
    }
)


class _ExpectedType:
    __slots__ = (
        "type",
        "order",
        "is_null",
        "is_builtin",
        "is_enum",
        "is_model",
        "is_class",
        "is_forward_ref",
        "is_any",
        "signature_matcher",
        "_resolved",
    )

    def __init__(self, typ_: typing.Type[typing.Any], order: int) -> None:
        # Early normalization
        if typ_ is None:
            typ_ = NoneType

        self.type: type = typ_
        self.order: int = order
        self.signature_matcher: typing.Optional[_ClassSignatureMatcher] = None

        self.is_forward_ref = isinstance(typ_, (ForwardRef, str))
        self._resolved = not self.is_forward_ref

        self.is_any = is_any_type(typ_)

        if self.is_any:
            self._set_any_defaults()
        elif self.is_forward_ref:
            self._set_forward_ref_defaults()
        else:
            # Full introspection
            self._introspect_type()

    def is_null_type(self) -> bool:
        if self.is_class:
            name = getattr(self.type, "__name__", None)
            if name is None:
                return False
            return name == "NoneType"
        return self.type is NoneType

    def isinstance_of(self, value: typing.Any) -> bool:
        if self.is_any:
            return True
        return isinstance(value, self.type)

    def _set_any_defaults(self) -> None:
        """Set defaults for Any type (fast path)."""
        self.is_null = False
        self.is_builtin = True
        self.is_enum = False
        self.is_model = False
        self.is_class = False
        self._resolved = True

    def _set_forward_ref_defaults(self) -> None:
        """Set defaults for forward references (fast path)."""
        self.is_null = False
        self.is_builtin = False
        self.is_enum = False
        self.is_model = False
        self.is_class = False

    def _introspect_type(self) -> None:
        """Perform full type introspection."""
        typ_ = self.type

        # Check for None type first
        self.is_null = typ_ is NoneType

        if self.is_null:
            self.is_builtin = True
            self.is_enum = False
            self.is_model = False
            self.is_class = False
            return

        is_type_class = isinstance(typ_, type)
        self.is_class = is_type_class

        # Fast builtin check
        if typ_ in _BUILTIN_TYPES:
            self.is_builtin = True
        else:
            origin = get_origin(typ_)
            self.is_builtin = origin in _BUILTIN_TYPES if origin else False

        # Enum check
        if is_type_class:
            try:
                self.is_enum = issubclass(typ_, Enum)
            except TypeError:
                self.is_enum = False
        else:
            self.is_enum = False

        self.is_model = PYDANTIC_MINI_MODEL_CONFIG in getattr(
            typ_, "__dict__", {}
        ) or is_dataclass(typ_)

    def resolve_type(
        self,
        globalns: typing.Optional[typing.Dict[str, typing.Any]] = None,
        localns: typing.Optional[typing.Dict[str, typing.Any]] = None,
    ) -> "_ExpectedType":
        """Resolve forward references to concrete types.

        Args:
            globalns: Global namespace for type resolution
            localns: Local namespace for type resolution

        Returns:
            Self with resolved type information
        """
        if self._resolved:
            return self

        forward_type = self.type
        if isinstance(forward_type, str):
            forward_type = ForwardRef(forward_type)

        resolved_type = resolve_and_cache_forward_ref(
            forward_type, globalns=globalns, localns=localns
        )

        self._update_from_resolved_type(resolved_type)
        self._resolved = True
        self.is_forward_ref = False

        return self

    def _update_from_resolved_type(self, resolved_type: typing.Any) -> None:
        """Update instance attributes based on resolved type."""
        temp_type = _ExpectedType(resolved_type, self.order)

        self.type = resolved_type
        self.is_builtin = temp_type.is_builtin
        self.is_enum = temp_type.is_enum
        self.is_model = temp_type.is_model
        self.is_class = temp_type.is_class

    def get_signature_matcher(self) -> _ClassSignatureMatcher:
        if getattr(self, "signature_matcher", None) is None:
            self.signature_matcher = getattr(
                self.type, PYDANTIC_MINI_SIGNATURE_MATCHER, None
            )
            if self.signature_matcher is None:
                self.signature_matcher = _ClassSignatureMatcher(self.type)
        return self.signature_matcher

    def matches(self, data: typing.Dict[str, typing.Any]) -> bool:
        if self.is_null_type():
            return False

        matcher = self.get_signature_matcher()

        if not matcher:
            return False

        if self.is_model:
            # Dataclasses don't support **kwargs in the standard sense unless
            # custom __init__ is defined, so we stick to field names.
            return matcher.required.issubset(data.keys()) and set(data.keys()).issubset(
                matcher.allowed
            )
        else:
            # All required parameters MUST be in the dict.
            if not matcher.required.issubset(data.keys()):
                return False

            # If the class DOES NOT have **kwargs, keys must be a subset of field names.
            # If the class DOES have **kwargs, any extra keys are allowed.
            if not matcher.has_kwargs and not set(data.keys()).issubset(
                matcher.allowed
            ):
                return False

            return True

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
    __slots__ = (
        "_actual_types",
        "model_config",
        "module_context",
        "has_any",
        "_finalised",
    )

    def __init__(
        self,
        actual_types: typing.Tuple[type],
        model_config: ModelConfigWrapper,
    ) -> None:
        """
        Validate and coerce datatype
        :param actual_types: Tuple of types to validate
        :param model_config: Model configuration
        """
        if not actual_types:
            raise TypeError("No types were provided")

        self._actual_types: typing.List[_ExpectedType] = []

        self.has_any: bool = False

        for index, typ in enumerate(actual_types):
            expected_type = _ExpectedType(typ, order=index)

            if expected_type not in self._actual_types:
                if expected_type.is_forward_ref and model_config.forward_refs_as_any:
                    self.has_any = True
                    expected_type.type = typing.Any
                    expected_type.is_forward_ref = False
                    expected_type._resolved = True

                if not self.has_any:
                    self.has_any = expected_type.is_any
                self._actual_types.append(expected_type)

        self._actual_types = sorted(self._actual_types, key=lambda t: t.order)

        self.model_config = model_config
        self.module_context: typing.Dict[str, typing.Any] = {}

        self._finalised = False

    def finalize(self):
        if self._finalised:
            return

        # Separated to speed-up called to finalize because there is no attribute
        # update request for finalized resolver
        config = self.model_config

        if not config.should_typecheck():
            self._finalised = True
            return

        for et in self._actual_types:
            if et.is_forward_ref:
                et.resolve_type(globalns=self.module_context)

        self._finalised = True

    def type_string(self) -> str:
        if self._actual_types:
            return ", ".join([str(t) for t in self._actual_types])  # type: ignore
        return ""

    def validate(self, value: typing.Any) -> bool:
        """Check if value matches any of the expected types"""
        return self.get_matching_type(value) is not None

    def coerce(self, value: typing.Any) -> typing.Any:
        """Convert value to one of the expected types"""
        matching_type = self.get_matching_type(value)

        if matching_type is None:
            raise TypeError(
                f"Cannot coerce {type(value).__name__!r} to any of the type(s) {self.type_string()!r}"
            )

        if matching_type.is_any:
            return value

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
        config = self.model_config

        any_expected_type = None

        for expected_type in self._actual_types:
            if expected_type.is_any:
                any_expected_type = expected_type

            if expected_type.isinstance_of(value):
                return expected_type

        # coercion type detection section
        if config.should_coerce():
            if isinstance(value, dict):
                for expected_type in self._actual_types:
                    if expected_type.is_class and expected_type.matches(value):
                        return expected_type

            for expected_type in self._actual_types:
                if expected_type.is_builtin or expected_type.is_enum:
                    try:
                        expected_type(value)
                        return expected_type
                    except (ValueError, TypeError):
                        continue

        if any_expected_type:
            return any_expected_type
        return None

    def _instantiate_from_dict(
        self, _expected_type: _ExpectedType, data: typing.Dict[str, typing.Any]
    ) -> typing.Any:
        """Instantiate a class from a dictionary"""
        return _expected_type(**data)


class _MiniFieldBase:

    __slots__ = (
        "init",
        "name",
        "private_name",
        "_mini_annotated_type",
        "_actual_annotated_type",
        "_query",
        "_default",
        "_default_factory",
        "_field_validator",
        "_preformat_callback",
        "model_context",
        "model_config",
        "disable_type_check",
    )

    def __init__(
        self,
        name: str,
        mini_annotated: Annotated,
        model_config: ModelConfigWrapper,
        init: bool = False,
        dc_field_obj: typing.Optional[Field] = None,
    ):
        if not is_mini_annotated(mini_annotated):
            raise ValidationError(
                "Field '{}' should be annotated with 'MiniAnnotated'.".format(name),
                params={"field": name, "annotation": mini_annotated},
            )
        self.init = init
        self.name = name
        self.private_name = make_private_field(name)

        self.model_config = model_config

        # type decomposition
        self._mini_annotated_type = mini_annotated
        self._actual_annotated_type = mini_annotated.__args__[0]
        self._query: Attrib = mini_annotated.__metadata__[0]

        self._field_validator: typing.Optional[ValidatorType] = None
        self._preformat_callback: typing.Optional[PreFormatType] = None

        self.model_context: typing.Optional[typing.Dict[str, typing.Any]] = None
        self.disable_type_check = not model_config.should_typecheck()

        if self._actual_annotated_type is typing.Any and not self.disable_type_check:
            self.disable_type_check = True

        # default value handler
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

    def processor_default_value(self, value: typing.Any) -> typing.Any:
        if isinstance(value, MiniField):
            value = value.get_default()
            if value is MISSING:
                raise AttributeError(
                    "No value provided for field '{}'".format(self.name)
                )
        return value

    def run_preformatters(self, instance: "BaseModel", value: typing.Any) -> typing.Any:
        if self._preformat_callback:
            try:
                value = self._preformat_callback(instance, value)
            except Exception as e:
                raise RuntimeError(
                    f"Preprocessor failed to process value '{value}'"
                ) from e

        return value

    def run_validators(self, instance: "BaseModel", value: typing.Any) -> typing.Any:
        if self._field_validator:
            try:
                status = self._field_validator(instance, value)
                if status is False:
                    raise ValidationError(
                        f"Validation of field {self.name!r} with value {value!r} failed.",
                        field=self.name,
                        value=value,
                        params={
                            "validator": self._field_validator.__name__,
                        },
                    )
            except Exception as e:
                # if isinstance(e, ValidationError):
                #     raise
                # raise ValidationError("Validation error") from e
                err = process_validator_errors(
                    instance,
                    self.name,
                    value=value,
                    error=e,
                    aggregate_errors=self.model_config.schema_mode,
                )
                if err:
                    raise err

    def _init_type_expectations(
        self,
        instance: "BaseModel",
        resolve_forward_ref: bool = True,
    ):
        pass

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
        raise NotImplementedError

    def set_validator(self, func: ValidatorType) -> None:
        self._field_validator = func

    def set_preformat_callback(self, func: PreFormatType) -> None:
        self._preformat_callback = func


class InitVarMiniField(_MiniFieldBase):
    __slots__ = ()

    # Init var


class DisableAllValidationMiniField(_MiniFieldBase):
    __slots__ = ()

    # NOTED: Removed all type introspections and validators since all validations are disabled
    def __init__(
        self,
        name: str,
        mini_annotated: Annotated,
        model_config: ModelConfigWrapper,
        init: bool = True,
        dc_field_obj: typing.Optional[Field] = None,
    ):
        self.init = init
        self.name = name
        self.private_name = make_private_field(name)

        self._query: Attrib = mini_annotated.__metadata__[0]

        self._field_validator: typing.Optional[ValidatorType] = None
        self._preformat_callback: typing.Optional[PreFormatType] = None

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

    def __set__(self, instance: "BaseModel", value: typing.Any) -> None:
        value = self.processor_default_value(value)

        value = self.run_preformatters(instance, value)

        instance.__dict__[self.private_name] = value
        return value


class MiniField(_MiniFieldBase):

    __slots__ = (
        "expected_type",
        "inner_type",
        "_inner_type_args",
        "type_annotation_args",
        "is_collection",
        "forward_ref_type_name",
    )

    def __init__(
        self,
        name: str,
        mini_annotated: Annotated,
        model_config: ModelConfigWrapper,
        init: bool = True,
        dc_field_obj: typing.Optional[Field] = None,
    ):
        super().__init__(name, mini_annotated, model_config, init, dc_field_obj)

        self.type_annotation_args: typing.Optional[typing.Tuple[typing.Any]] = (
            self.type_can_be_validated(
                self._actual_annotated_type, resolve_forward_ref=False
            )
        )

        self._inner_type_args = get_args(self._actual_annotated_type)

        self.is_collection, _ = is_collection(self._actual_annotated_type)

        self.expected_type: typing.Optional[_ExpectedTypeResolver] = None
        self.inner_type: typing.Optional[_ExpectedTypeResolver] = None

        self.forward_ref_type_name: typing.Optional[str] = get_forward_type(
            self._actual_annotated_type
        )

    def _init_type_expectations(
        self,
        instance: "BaseModel",
        resolve_forward_ref: bool = True,
    ):
        if self.model_config.forward_refs_as_any:
            resolve_forward_ref = False

        self.type_annotation_args: typing.Optional[typing.Tuple[typing.Any]] = (
            self.type_can_be_validated(
                self._actual_annotated_type,
                instance=instance,
                resolve_forward_ref=resolve_forward_ref,
            )
        )

        self.expected_type = _ExpectedTypeResolver(
            actual_types=self.type_annotation_args,
            model_config=self.model_config,
        )

        inner_types_list: typing.List[type] = []

        for t in self._inner_type_args:
            if t not in inner_types_list:
                typ = get_type(
                    t,
                    globalns=self.get_model_context(
                        instance, cache_context=resolve_forward_ref
                    ),
                    resolve_forward_ref=resolve_forward_ref,
                )
                if typ is not None:
                    inner_types_list.append(typ)

        try:
            self.inner_type = _ExpectedTypeResolver(
                actual_types=tuple(inner_types_list),  # type: ignore
                model_config=self.model_config,
            )
        except TypeError:
            self.inner_type = None

    def _finalise_type_resolver(self):
        if self.expected_type:
            self.expected_type.finalize()

        if self.inner_type:
            self.inner_type.finalize()

    def __set__(self, instance: "BaseModel", value: typing.Any) -> None:
        value = self.processor_default_value(value)

        value = self.run_preformatters(instance, value)

        if not self.disable_type_check:
            model_context = self.get_model_context(instance)
            self.expected_type.module_context = model_context
            if self.inner_type:
                self.inner_type.module_context = model_context

            self._finalise_type_resolver()

            coerced_value = self._value_coerce(value)
            if coerced_value is not None:
                value = coerced_value
            self._field_type_validator(value)
        else:
            # run other field validators when type checking is disabled
            self._query.validate(value, self.name)

        self.run_validators(instance, value)

        instance.__dict__[self.private_name] = value
        return None

    @staticmethod
    def get_model_context(
        instance: "BaseModel", cache_context: bool = True
    ) -> typing.Optional[typing.Dict[str, typing.Any]]:
        if instance is None:
            return None
        cls = instance.__class__
        context = getattr(cls, PYDANTIC_MINI_MODEL_CONTEXT, None)
        if context:
            return context

        context = getattr(inspect.getmodule(cls), "__dict__", None)
        if cache_context:
            setattr(cls, PYDANTIC_MINI_MODEL_CONTEXT, context)

        return context

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

    def _field_type_validator(self, value: typing.Any) -> None:
        if self.is_collection:
            if self.inner_type:
                # old_config = self.inner_type.model_config
                # if not self.inner_type.model_config.should_typecheck():

                # new_config = old_config.copy(validation=ValidationFlags.TYPECHECK)
                # self.inner_type.model_config = new_config

                for val in value:
                    if not self.inner_type.validate(val):
                        raise TypeError(
                            f"Expected a collection of values of type(s) '{self.inner_type.type_string()}'. Value: {val} "
                        )

                # self.inner_type.model_config = old_config
            #  del new_config
        elif not self.expected_type.validate(value):
            raise TypeError(
                f"Field '{self.name!r}' should be of type {self.expected_type.type_string()}, "
                f"but got {type(value).__name__}."
            )

        self._query.validate(value, self.name)

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
                        globalns=self.get_model_context(
                            instance, cache_context=resolve_forward_ref
                        ),
                        resolve_forward_ref=resolve_forward_ref,
                    )
                    if _arg_type is not None:
                        _set.add(_arg_type)

                return tuple(_set)
        else:
            return (
                get_type(
                    typ,
                    globalns=self.get_model_context(
                        instance, cache_context=resolve_forward_ref
                    ),
                    resolve_forward_ref=resolve_forward_ref,
                ),
            )

        return None
