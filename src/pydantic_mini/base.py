import typing
import keyword
import inspect
from collections import OrderedDict
from dataclasses import dataclass, Field, field, MISSING
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
)
from .fields import MiniField, _ClassSignatureMatcher, DisableAllValidationMiniField


__all__ = ("BaseModel",)

PYDANTIC_MINI_EXTRA_MODEL_CONFIG = "__pydantic_mini_extra_config__"


class SchemaMeta(type):

    def __new__(cls, name, bases, attrs, **kwargs):
        parents = [b for b in bases if isinstance(b, SchemaMeta)]
        if not parents:
            return super().__new__(cls, name, bases, attrs)

        new_attrs = cls.build_class_namespace(name, attrs)

        validators, preformatters = cls._collect_field_callbacks(new_attrs, bases)

        # Store them in the namespace for later access
        new_attrs["__validators__"] = validators
        new_attrs["__preformatters__"] = preformatters

        config = cls._prepare_model_fields(new_attrs, validators, preformatters)

        new_class = super().__new__(cls, name, bases, new_attrs, **kwargs)

        non_dataclass_config: typing.Dict[str, typing.Any] = (
            config.get_non_dataclass_config()
        )

        setattr(new_class, PYDANTIC_MINI_EXTRA_MODEL_CONFIG, non_dataclass_config)

        new_class = dataclass(new_class, **config.get_dataclass_config())  # type: ignore

        # Let's activate the fields for type checking
        if not non_dataclass_config["disable_all_validation"]:

            for field_name in new_attrs.get("__annotations__", {}):
                mini_field = new_attrs.get(field_name, None)
                if isinstance(mini_field, MiniField):
                    # Initialise type expectations with the fully realised class
                    mini_field._init_type_expectations(
                        new_class, resolve_forward_ref=False, model_config=non_dataclass_config
                    )

        matcher = _ClassSignatureMatcher(new_class)
        setattr(new_class, "__signature_matcher__", matcher)

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
    ) -> ModelConfigWrapper:
        ann_with_defaults = OrderedDict()
        ann_without_defaults = OrderedDict()

        model_config_class: typing.Optional[typing.Type] = attrs.get("Config", None)
        config = ModelConfigWrapper(model_config_class)

        config_dict = config.get_non_dataclass_config()

        disable_all_validation = config_dict.get("disable_all_validation", False)
        disable_type_check = config_dict.get("disable_type_check", False)

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
                        f"Field '{field_name}' does not have type annotation. "
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
                    actual_type = getattr(annotation, "type", get_args(annotation))
                    if isinstance(actual_type, (tuple, list)):
                        if actual_type:
                            actual_type = actual_type[0]
                        else:
                            actual_type = object
                    annotation = MiniAnnotated[actual_type, Attrib()]
                else:
                    annotation = MiniAnnotated[object, Attrib()]
                    disable_type_check = True

                if disable_all_validation:
                    attrs[field_name] = DisableAllValidationMiniField(field_name, annotation, value_field)
                else:
                    attrs[field_name] = MiniField(field_name, annotation, value_field, disable_type_check=disable_type_check)

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
            attrib = annotation.__metadata__[0]

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

            value_field = cls.coerce_value_to_dataclass_field(field_name, attrs, value)

            if disable_all_validation:
                mini_field = DisableAllValidationMiniField(
                    field_name, annotation, value_field
                )
            else:
                mini_field = MiniField(field_name, annotation, value_field, disable_type_check=disable_type_check)

                if field_name in validators:
                    for validator_func in validators[field_name]:
                        mini_field.add_validator(validator_func)

                if field_name in preformatters:
                    for preformat_func in preformatters[field_name]:
                        mini_field.add_preformat_callback(preformat_func)

            attrs[field_name] = mini_field

        ann_without_defaults.update(ann_with_defaults)

        if ann_without_defaults:
            attrs["__annotations__"] = ann_without_defaults

        return config


class PreventOverridingMixin:

    _protect = ["__init__"]

    def __init_subclass__(cls, **kwargs):
        if cls.__name__ != "BaseModel":
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
