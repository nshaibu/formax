import typing
import keyword
import inspect
from collections import OrderedDict
from dataclasses import dataclass, Field, field, MISSING, fields
from .formatters import BaseModelFormatter
from .typing import (
    is_mini_annotated,
    get_type,
    get_args,
    get_forward_type,
    MiniAnnotated,
    Attrib,
    is_optional_type,
    is_initvar_type,
    is_class_var_type,
    ModelConfigWrapper,
    resolve_annotations,
    dataclass_transform,
    ValidatorType,
    PreFormatType,
    ValidationFlags,
    InitStrategy,
)
from .utils import (
    make_private_field,
    PYDANTIC_MINI_MODEL_CONFIG,
    PYDANTIC_MINI_MODEL_CONTEXT,
    PYDANTIC_MINI_SIGNATURE_MATCHER,
    PYDANTIC_MINI_ERROR_COLLECTOR,
)
from .make_init import (
    make_disable_all_validation_init,
    make_disable_type_check_init,
    make_fast_init,
)
from .exceptions import ValidationError, ValidationErrorCollector
from .utils import process_validator_errors
from .fields import (
    MiniField,
    _ClassSignatureMatcher,
    DisableAllValidationMiniField,
    InitVarMiniField,
)


__all__ = ("BaseModel",)


def wrap_schema_mode_init(cls) -> typing.Callable[[typing.Any], None]:
    orig_init = cls.__init__

    def new_init(self, *args, **kwargs):
        collector = ValidationErrorCollector()
        object.__setattr__(self, PYDANTIC_MINI_ERROR_COLLECTOR, collector)

        orig_init(self, *args, **kwargs)

        collector.raise_if_errors()
        del collector

    return new_init


def _generate_fast_init(
    attrs: typing.Dict[str, typing.Any],
    config: ModelConfigWrapper,
) -> typing.Callable[[typing.Any], typing.Any]:
    if config.validation & ValidationFlags.VALIDATED:
        if config.validation & ValidationFlags.TYPECHECK:
            return make_fast_init(attrs)
        else:
            return make_disable_type_check_init(attrs)

    return make_disable_all_validation_init(attrs)


def _add_private_attr_slots(attrs: typing.Dict[str, typing.Any]) -> None:
    dc_fields = set([name for name in attrs.get("__annotations__", [])])
    slots: typing.Union[str, typing.Tuple[str]] = attrs.get("__slots__")
    if not slots:
        return

    if isinstance(slots, str):
        slots = (slots,)
    else:
        slots = tuple(slots)

    private_slots = [PYDANTIC_MINI_ERROR_COLLECTOR]

    for fd in dc_fields:
        private_name = make_private_field(fd)
        if private_name not in slots:
            private_slots.append(private_name)

    if private_slots:
        attrs["__slots__"] = tuple(private_slots) + slots


def compile_callbacks(
    callbacks: typing.List[typing.Union[PreFormatType, ValidatorType]],
    name: str,
    field_name: str,
    callback_type: typing.Literal["validate", "preformat"],
    attrib_query: typing.Optional[Attrib] = None,
    aggregate_errors: bool = False,
) -> typing.Union[PreFormatType, ValidatorType]:
    lines = [f"def {name}_{callback_type}(instance, value):"]

    if callback_type == "validate":
        _callbacks = sorted(
            callbacks, key=lambda func: getattr(func, "_validator_order", 0)
        )

        # Inbuilt validators
        if attrib_query:
            lines.append(
                f"\tattrib_query_{field_name}.validate(instance, value, {field_name!r}, {aggregate_errors})\n"
            )

        for i, cb in enumerate(_callbacks):
            params = {"validator": cb.__name__}
            lines.append("\ttry:")
            lines.append(f"\t\tif _cb{i}(instance, value) is False:")
            lines.append(
                f"\t\t\traise ValidationError('Validation of field {field_name} failed.', field_name={field_name!r}, value=value, params={params})"
            )
            lines.append("\texcept Exception as err:")

            # Error parsing
            lines.append(
                f"\t\terr = process_validator_errors(instance, {field_name!r}, value, err, {aggregate_errors})"
            )
            lines.append(f"\t\tif err:\n\t\t\traise err")

        lines.append("\treturn None")
    else:
        _callbacks = sorted(
            callbacks, key=lambda func: getattr(func, "_preformat_order", 0)
        )

        for i, cb in enumerate(_callbacks):
            lines.append(f"\tvalue = _cb{i}(instance, value)")
        lines.append("\treturn value")

    code = "\n".join(lines)

    global_ns = {f"_cb{i}": cb for i, cb in enumerate(callbacks)}
    global_ns["ValidationError"] = ValidationError  # type: ignore
    global_ns["process_validator_errors"] = process_validator_errors  # type: ignore
    global_ns[f"attrib_query_{field_name}"] = attrib_query  # type: ignore

    local_ns = {}

    exec(code, global_ns, local_ns)

    return local_ns[f"{name}_{callback_type}"]


class SchemaMeta(type):

    def __new__(cls, name, bases, attrs, **kwargs):
        parents = [b for b in bases if isinstance(b, SchemaMeta)]
        if not parents:
            return super().__new__(cls, name, bases, attrs)

        new_attrs = cls.build_class_namespace(name, attrs)

        model_config_class: typing.Optional[typing.Type] = new_attrs.get("Config", None)
        config = ModelConfigWrapper(model_config_class)

        validators, preformatters = cls._collect_field_callbacks(
            new_attrs, bases, config
        )

        # Store them in the namespace for later access
        new_attrs["__validators__"] = validators
        new_attrs["__preformatters__"] = preformatters
        new_attrs[PYDANTIC_MINI_MODEL_CONTEXT] = None

        cls._prepare_model_fields(new_attrs, validators, preformatters, config)
        dataclass_config: typing.Dict[str, typing.Any] = config.as_dataclass_kwargs()

        if config.init_strategy == InitStrategy.FAST:
            dataclass_config["init"] = False
            fast_init = _generate_fast_init(new_attrs, config)
            new_attrs["__init__"] = fast_init
        elif config.init_strategy == InitStrategy.CUSTOM:
            dataclass_config["init"] = False
            if "__init__" not in new_attrs:
                raise KeyError("'__init__' is not defined for class '{}'".format(name))
        else:
            dataclass_config["init"] = True

        if dataclass_config["frozen"]:
            _add_private_attr_slots(new_attrs)

        new_attrs[PYDANTIC_MINI_MODEL_CONFIG] = config

        new_class = super().__new__(cls, name, bases, new_attrs, **kwargs)

        new_class = dataclass(new_class, **dataclass_config)  # type: ignore

        if config.schema_mode:
            new_class.__init__ = wrap_schema_mode_init(new_class)

        # Let's activate the fields for type checking
        if config.should_typecheck():
            for field_name in new_attrs.get("__annotations__", {}):
                mini_field = new_attrs.get(field_name, None)
                if isinstance(mini_field, MiniField):
                    # Initialise type expectations with the fully realised class
                    mini_field._init_type_expectations(
                        new_class,
                        resolve_forward_ref=False,
                    )

        matcher = _ClassSignatureMatcher(new_class)
        setattr(new_class, PYDANTIC_MINI_SIGNATURE_MATCHER, matcher)

        return new_class

    @classmethod
    def build_class_namespace(
        cls, name: str, attrs: typing.Dict[str, typing.Any]
    ) -> typing.Dict[str, typing.Any]:
        new_attrs = attrs.copy()

        # Parse annotation by class
        if "__annotations__" in attrs:
            temp_class = type(f"{name}Temp", (object,), attrs)
            resolved_hints = resolve_annotations(
                temp_class,
                global_ns=getattr(inspect.getmodule(temp_class), "__dict__", None),
            )

            for field_name, resolved_type in resolved_hints.items():
                new_attrs["__annotations__"][field_name] = resolved_type

        return new_attrs

    @classmethod
    def _collect_field_callbacks(
        cls,
        attrs: typing.Dict[str, typing.Any],
        bases: typing.Tuple[type, ...],
        config: ModelConfigWrapper,
    ) -> typing.Tuple[
        typing.Dict[str, typing.List[ValidatorType]],
        typing.Dict[str, typing.List[PreFormatType]],
    ]:
        """
        Collect all validators and preformatters from the class namespace.
        This runs once during class creation - zero-runtime overhead.

        Returns:
            Tuple of (validators_dict, preformatters_dict)
        """
        validators: typing.Dict[str, typing.List[ValidatorType]] = {}
        preformatters: typing.Dict[str, typing.List[PreFormatType]] = {}

        for attr_name, attr_value in attrs.items():
            if not callable(attr_value):
                continue

            if isinstance(attr_value, (classmethod, staticmethod, property)):
                continue

            if attr_name.startswith("__"):
                continue

            attr_value = typing.cast(
                typing.Union[ValidatorType, PreFormatType], attr_value
            )

            if hasattr(attr_value, "_validator_fields"):
                for field_name in attr_value._validator_fields:  # type: ignore[attr-defined]
                    validators.setdefault(field_name, []).append(attr_value)

            if hasattr(attr_value, "_preformat_fields"):
                for field_name in attr_value._preformat_fields:  # type: ignore[attr-defined]
                    preformatters.setdefault(field_name, []).append(attr_value)

        for base in bases:
            if hasattr(base, "__validators__"):
                for field_name, field_validators in base.__validators__.items():
                    validators.setdefault(field_name, []).extend(field_validators)

            if hasattr(base, "__preformatters__"):
                for field_name, field_preformatters in base.__preformatters__.items():
                    preformatters.setdefault(field_name, []).extend(field_preformatters)

        return validators, preformatters

    @classmethod
    def get_non_annotated_fields(
        cls, attrs, exclude: typing.Optional[typing.Tuple[typing.Any]] = None
    ):
        if exclude is None:
            exclude = []

        for field_name, value in attrs.items():
            if isinstance(value, (classmethod, staticmethod, property)):
                continue

            # ignore ABC class internal state manager
            if "_abc_impl" == field_name:
                continue

            if (
                not field_name.startswith("__")
                and field_name not in exclude
                and not callable(value)
            ):
                if isinstance(value, Field):
                    typ = cls._figure_out_field_type_by_default_value(
                        field_name, value, attrs
                    )
                else:
                    typ = cls._figure_out_field_type_by_default_value(
                        field_name, value, attrs
                    )
                    value = field(default=value)

                if typ is not None:
                    yield field_name, typ, value

    @classmethod
    def get_fields(
        cls, attrs
    ) -> typing.List[typing.Tuple[typing.Any, typing.Any, typing.Any]]:
        field_dict = {}

        annotation_fields = attrs.get("__annotations__", {})

        for field_name, annotation in annotation_fields.items():
            field_tuple = field_name, annotation
            value = MISSING
            if field_name in attrs:
                value = attrs[field_name]
                value = value if isinstance(value, Field) else field(default=value)

            field_tuple = (*field_tuple, value)

            field_dict[field_name] = field_tuple

        # get fields without annotation
        for field_name, annotation, value in cls.get_non_annotated_fields(
            attrs, exclude=tuple(field_dict.keys())
        ):
            field_dict[field_name] = field_name, annotation, value

        return list(field_dict.values())

    @classmethod
    def _figure_out_field_type_by_default_value(
        cls, field_name: str, value: Field, attrs: typing.Dict[str, typing.Any]
    ) -> typing.Any:
        if isinstance(value, Field):
            if value.default is not MISSING:
                return type(value.default)
            elif value.default_factory is not MISSING:
                return type(value.default_factory())
        elif hasattr(value, "__class__"):
            return value.__class__
        else:
            if field_name in attrs:
                return type(value)
        return typing.Any

    @staticmethod
    def coerce_value_to_dataclass_field(
        field_name: str,
        attrs: typing.Dict[str, typing.Any],
        default_value: typing.Any = MISSING,
    ) -> Field:
        value = attrs.get(field_name, default_value)
        if not isinstance(value, Field):
            if value is MISSING:
                value = field()
            else:
                value = field(default=value)
        return value

    @classmethod
    def _prepare_model_fields(
        cls,
        attrs: typing.Dict[str, typing.Any],
        validators: typing.Dict[str, typing.List[ValidatorType]],
        preformatters: typing.Dict[str, typing.List[PreFormatType]],
        config: ModelConfigWrapper,
    ) -> None:
        ann_with_defaults = OrderedDict()
        ann_without_defaults = OrderedDict()

        disable_all_validation = config.validation == ValidationFlags.NONE

        for field_name, annotation, value in cls.get_fields(attrs):
            if not isinstance(field_name, str) or not field_name.isidentifier():
                raise TypeError(
                    f"Field names must be valid identifiers: {field_name!r}"
                )
            if keyword.iskeyword(field_name):
                raise TypeError(f"Field names must not be keywords: {field_name!r}")

            if annotation is None:
                if value not in (MISSING, None):
                    annotation = cls._figure_out_field_type_by_default_value(
                        field_name, value, attrs
                    )

                if annotation is None:
                    raise TypeError(
                        f"Field {field_name!r} does not have type annotation. "
                        f"Figuring out field type from default value failed"
                    )

            if (
                is_initvar_type(annotation)
                or is_class_var_type(annotation)
                or annotation is typing.Any
            ):
                # let's ignore init-var and class-var, dataclass will take care of them
                # typing.Any does not require any type Validation
                ann_with_defaults[field_name] = annotation

                value_field = cls.coerce_value_to_dataclass_field(
                    field_name, attrs, value
                )
                if annotation is not typing.Any:
                    # actual_type = getattr(annotation, "type", get_args(annotation))
                    # if isinstance(actual_type, (tuple, list)):
                    #     if actual_type:
                    #         actual_type = actual_type[0]
                    #     else:
                    #         actual_type = object
                    # annotation = MiniAnnotated[actual_type, Attrib()]
                    continue
                else:
                    annotation = MiniAnnotated[object, Attrib()]

                if disable_all_validation:
                    attrs[field_name] = DisableAllValidationMiniField(
                        field_name, annotation, config, value_field.init, value_field
                    )
                else:
                    mini_field = MiniField(
                        field_name,
                        annotation,
                        config,
                        value_field.init,
                        value_field,
                    )

                    cls.validator_hook(
                        mini_field,
                        Attrib(),
                        field_name,
                        validators.get(field_name, []),
                        config.schema_mode,
                    )

                    cls.preformat_hook(
                        mini_field, field_name, preformatters.get(field_name, [])
                    )

                    attrs[field_name] = mini_field

                continue

            if not is_mini_annotated(annotation):
                if get_type(annotation, resolve_forward_ref=False) is None:
                    # Let's confirm that the annotation isn't a forward type
                    forward_annotation = get_forward_type(annotation)
                    if forward_annotation is None:
                        raise TypeError(
                            f"Field '{field_name!r}' must be annotated with a real type. {annotation} is not a type"
                        )

                annotation = MiniAnnotated[
                    annotation,
                    Attrib(
                        default=value.default if isinstance(value, Field) else value,
                        default_factory=(
                            value.default_factory if isinstance(value, Field) else value
                        ),
                    ),
                ]

            annotation_type = annotation.__args__[0]
            attrib: Attrib = annotation.__metadata__[0]

            if is_optional_type(annotation_type):
                # all optional annotations without default value will have
                # None as default
                if not attrib.has_default():
                    attrib.default = None
                    attrs[field_name] = field(default=None)

            if value is MISSING:
                if attrib.has_default():
                    if attrib.default is not MISSING:
                        attrs[field_name] = field(default=attrib.default)
                    else:
                        attrs[field_name] = field(
                            default_factory=attrib.default_factory
                        )

            if attrib.has_default():
                ann_with_defaults[field_name] = annotation
            else:
                ann_without_defaults[field_name] = annotation

            if attrib.has_pre_formatter():
                preformatters.setdefault(field_name, []).append(attrib.pre_formatter)

            if attrib.has_validators():
                validators.setdefault(field_name, []).extend(attrib.validators)

            value_field = cls.coerce_value_to_dataclass_field(field_name, attrs, value)

            if disable_all_validation:
                mini_field = DisableAllValidationMiniField(
                    field_name, annotation, config, value_field.init, value_field
                )
            else:
                mini_field = MiniField(
                    field_name, annotation, config, value_field.init, value_field
                )

                cls.validator_hook(
                    mini_field,
                    attrib,
                    field_name,
                    validators.get(field_name, []),
                    config.schema_mode,
                )

                cls.preformat_hook(
                    mini_field, field_name, preformatters.get(field_name, [])
                )

            attrs[field_name] = mini_field

        ann_without_defaults.update(ann_with_defaults)

        if ann_without_defaults:
            attrs["__annotations__"] = ann_without_defaults

        return None

    @staticmethod
    def preformat_hook(
        mini_field: MiniField,
        field_name: str,
        preformat_list: typing.List[PreFormatType],
    ) -> None:
        if not preformat_list:
            return

        compiled_preformat_callback: PreFormatType = compile_callbacks(
            preformat_list, "field", field_name, "preformat"
        )
        mini_field.set_preformat_callback(compiled_preformat_callback)

    @staticmethod
    def validator_hook(
        mini_field: MiniField,
        attrib_query: Attrib,
        field_name: str,
        validator_list: typing.List[ValidatorType],
        schema_mode: bool,
    ) -> None:
        compiled_validator: ValidatorType = compile_callbacks(
            validator_list,
            "field",
            field_name,
            "validate",
            attrib_query,
            schema_mode,
        )
        mini_field.set_validator(compiled_validator)


class PreventOverridingMixin:

    _protect = ["__init__"]

    def __init_subclass__(cls: "BaseModel", **kwargs):
        if cls.__name__ != "BaseModel":
            config = cls.get_pydantic_mini_config()
            if config.init_strategy in [InitStrategy.FAST, InitStrategy.CUSTOM]:
                return

            for attr_name in cls._protect:
                if attr_name in cls.__dict__:
                    raise PermissionError(
                        f"Model '{cls.__name__}' cannot override {attr_name!r}. "
                        f"Consider using __model_init__ for all your custom initialization"
                    )
        super().__init_subclass__(**kwargs)


@dataclass_transform(
    eq_default=True,
    order_default=False,
    kw_only_default=False,
    frozen_default=False,
    field_specifiers=(MiniAnnotated, Attrib),
)
class BaseModel(PreventOverridingMixin, metaclass=SchemaMeta):

    # These are populated by the metaclass
    __validators__: typing.Dict[str, typing.List[ValidatorType]]
    __preformatters__: typing.Dict[str, typing.List[PreFormatType]]

    __pydantic_mini_model_context__ = None

    @staticmethod
    def get_formatter_by_name(name: str) -> BaseModelFormatter:
        return BaseModelFormatter.get_formatter(format_name=name)

    @classmethod
    def loads(
        cls, data: typing.Any, _format: str
    ) -> typing.Union[typing.List["BaseModel"], "BaseModel"]:
        return cls.get_formatter_by_name(_format).encode(cls, data)

    def dump(self, _format: str) -> typing.Any:
        return self.get_formatter_by_name(_format).decode(instance=self)

    @classmethod
    def get_pydantic_mini_config(cls) -> ModelConfigWrapper:
        return getattr(cls, PYDANTIC_MINI_MODEL_CONFIG, None)
