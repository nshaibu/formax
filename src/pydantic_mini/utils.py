import typing

from .exceptions import ValidationError, ValidationErrorCollector

if typing.TYPE_CHECKING:
    from .base import BaseModel

PRIVATE_FIELD_PREFIX = "_pydantic_mini_"

PYDANTIC_MINI_MODEL_CONFIG = "__pydantic_mini_model_config__"

PYDANTIC_MINI_SIGNATURE_MATCHER = "__pydantic_mini_signature_matcher__"

PYDANTIC_MINI_MODEL_CONTEXT = "__pydantic_mini_model_context__"

_DATACLASS_CONFIG_PARAMS = "__dataclass_params__"

PYDANTIC_MINI_ERROR_COLLECTOR = "_pydantic_mini_internal_error_collect"


def make_private_field(field_name):
    return f"{PRIVATE_FIELD_PREFIX}{field_name}"


def process_validator_errors(
    instance: "BaseModel",
    field_name: str,
    value: typing.Any,
    error: Exception,
    aggregate_errors: bool,
) -> typing.Optional[Exception]:
    if aggregate_errors:
        collector: ValidationErrorCollector = getattr(
            instance, PYDANTIC_MINI_ERROR_COLLECTOR, []
        )
        if isinstance(error, ValidationError):
            error_list = []
            for err in error._errors:
                if not isinstance(err, dict):
                    continue
                if err.get("field") is None or err.get("input") is None:
                    err["field"] = field_name
                    err["input"] = value

                error_list.append(err)
            collector.errors.extend(error_list)
        else:
            collector.add_error(
                field=field_name,
                message=str(error),
                value=value,
                params={"exception_type": error.__class__.__name__},
            )

        return None

    return error
