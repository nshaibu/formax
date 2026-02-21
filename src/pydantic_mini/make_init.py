import typing
import inspect
from dataclasses import MISSING

from .fields import MiniField
from .utils import (
    make_private_field,
    PYDANTIC_MINI_MODEL_CONTEXT,
    PYDANTIC_INIT_VARS_FIELDS,
    process_validator_errors,
    PYDANTIC_MINI_MODEL_CONFIG,
)


def join_string(
    str_list: typing.Union[typing.List[str], typing.Tuple[str, ...]], sep: str = ","
) -> str:
    """Combine strings separated by sep."""
    if not str_list:
        return ""
    else:
        return sep.join(str_list) + sep


def _init_header(attrs: typing.Dict[str, typing.Any]) -> str:
    """Generate function signature: def __init__(self, field1, field2=default, ...)"""
    params = []
    default_params = []

    for field_name in attrs.get("__annotations__", []):
        mini_field: typing.Optional[MiniField] = attrs.get(field_name)

        if mini_field:
            default_value = mini_field.get_default()
            if default_value is not MISSING:
                # Field has default - use repr for proper quoting
                default_params.append(f"{field_name}={default_value!r}")
            else:
                # Required field
                params.append(field_name)
        else:
            # No MiniField found - required field
            params.append(field_name)

    args_tuple = ("self", *params, *default_params)
    args_str = join_string(args_tuple)

    return f"def __init__({args_str[:-1]}):"


def _post_init_call_codegen(attrs: typing.Dict[str, typing.Any]) -> str:
    init_fields = attrs.get(PYDANTIC_INIT_VARS_FIELDS, [])
    args_str = join_string(init_fields)
    lines = (
        f"\tself.__post_init__({args_str[:-1]})",
    )
    return "\n".join(lines)


def _disable_all_validation_init_body(
    attrs: typing.Dict[str, typing.Any], frozen: bool = False
) -> typing.Tuple[str, typing.Dict[str, typing.Any]]:
    body = []
    cbs = {}

    field_names = list(attrs.get("__annotations__", []))

    for field_name in field_names:
        cb_statement = ""
        mini_field: typing.Optional[MiniField] = attrs.get(field_name)
        if mini_field:
            if mini_field._preformat_callback:
                cb_name = f"preformat_{field_name}"
                cbs[cb_name] = mini_field._preformat_callback
                cb_statement = f"\t{field_name} = {cb_name}(self, {field_name})\n"

            private_name = make_private_field(field_name)
            statement = cb_statement + f"\tself.__dict__[{private_name!r}]={field_name}"
            body.append(statement)
        else:
            continue

    if '__post_init__' in attrs:
        body.append(_post_init_call_codegen(attrs))

    code = "\n".join(body)

    return code, cbs


def make_disable_all_validation_init(
    attrs: typing.Dict[str, typing.Any],
) -> typing.Callable[[typing.Any], typing.Any]:
    body_code, cbs = _disable_all_validation_init_body(attrs)
    statements = (_init_header(attrs), body_code)

    code = "\n".join(statements)

    local_ns = {}

    exec(code, cbs, local_ns)

    return local_ns["__init__"]


def _disable_type_check_init_body(
    attrs: typing.Dict[str, typing.Any], frozen: bool = False
) -> typing.Tuple[str, typing.Dict[str, typing.Any]]:
    body = []
    preformat_cbs = {}
    validator_cbs = {}
    validator_queries = {}

    field_names = list(attrs.get("__annotations__", []))

    for field_name in field_names:
        cb_statement = ""
        validator_cbs_statement = ""

        mini_field: typing.Optional[MiniField] = attrs.get(field_name)

        if mini_field:
            if mini_field._preformat_callback:
                cb_name = f"preformat_{field_name}"
                preformat_cbs[cb_name] = mini_field._preformat_callback
                cb_statement = f"\t{field_name} = {cb_name}(self, {field_name})\n"

            if mini_field._field_validator:
                vbs_name = f"field_validator_{field_name}"
                validator_cbs[vbs_name] = mini_field._field_validator
                validator_cbs_statement = f"\t{vbs_name}(self, {field_name})\n"

        else:
            continue

        private_name = make_private_field(field_name)
        statement = (
            cb_statement
            + validator_cbs_statement
            + f"\tself.__dict__[{private_name!r}]={field_name}"
        )
        body.append(statement)

    if '__post_init__' in attrs:
        body.append(_post_init_call_codegen(attrs))

    code = "\n".join(body)

    context = {**preformat_cbs, **validator_cbs, **validator_queries}

    return code, context


def make_disable_type_check_init(
    attrs: typing.Dict[str, typing.Any],
) -> typing.Callable[[typing.Any], typing.Any]:
    body_code, cbs = _disable_type_check_init_body(attrs)
    statements = (_init_header(attrs), body_code)

    code = "\n".join(statements)

    local_ns = {}

    exec(code, cbs, local_ns)

    return local_ns["__init__"]


def _fast_init_body(
    attrs: typing.Dict[str, typing.Any], frozen: bool = False
) -> typing.Tuple[str, typing.Dict[str, typing.Any]]:
    body = []
    mini_fields_dict = {}

    field_names = list(attrs.get("__annotations__", []))

    model_context_statement = (
        f"\tmodel_context = getattr(self, {PYDANTIC_MINI_MODEL_CONTEXT!r}, None)\n"
    )
    model_context_statement += f"\tif not model_context: model_context = getattr(inspect.getmodule(self), '__dict__', None)\n"
    model_config_statement = (
        f"\tmodel_config = getattr(self, {PYDANTIC_MINI_MODEL_CONFIG!r}, None)\n"
    )

    body.append(model_context_statement)
    body.append(model_config_statement)

    for field_name in field_names:
        mini_statement = ""

        mini_field: typing.Optional[MiniField] = attrs.get(field_name)

        if mini_field:
            mini_field_name = f"mini_field_{field_name}"
            mini_fields_dict[mini_field_name] = mini_field

            mini_statement = f"\tcoerced_{field_name}_value = {mini_field_name}.run_preformatters(self, {field_name})\n"

            if mini_field.__class__.__name__ == "MiniField":
                # Resolve and set model context
                # mini_statement += f"\tmodel_context_{field_name} = {mini_field_name}.get_model_context(self)\n"
                mini_statement += f"\t{mini_field_name}.expected_type.module_context = model_context\n"
                mini_statement += f"\tif {mini_field_name}.inner_type:\n"
                mini_statement += f"\t\t{mini_field_name}.inner_type.module_context = model_context\n\n"

                # Initialised type resolver
                mini_statement += f"\t{mini_field_name}._finalise_type_resolver()\n\n"

                # condition for coercing values
                mini_statement += "\ttry:\n"
                mini_statement += f"\t\tcoerced_{field_name} = {mini_field_name}._value_coerce(coerced_{field_name}_value)\n"
                mini_statement += f"\t\tif coerced_{field_name} is not None:\n"
                mini_statement += (
                    f"\t\t\tcoerced_{field_name}_value = coerced_{field_name}\n\n"
                )
                mini_statement += "\texcept Exception as err:\n"
                mini_statement += f"\t\terr = process_validator_errors(self,field_name={field_name!r},value=coerced_{field_name}_value,error=err,aggregate_errors=model_config.schema_mode)\n"
                mini_statement += f"\t\tif err:\n"
                mini_statement += f"\t\t\traise err\n"

                # validate value
                mini_statement += f"\t{mini_field_name}._field_type_validator(self, coerced_{field_name}_value)\n"

                mini_statement += f"\t{mini_field_name}.run_validators(self, coerced_{field_name}_value)\n\n"
        else:
            continue

        private_name = make_private_field(field_name)
        if frozen:
            mini_statement += f"\tobject.__setattr__(self, {private_name!r}, coerced_{field_name}_value)"
        else:
            mini_statement += (
                f"\tself.__dict__[{private_name!r}]=coerced_{field_name}_value\n"
            )
        body.append(mini_statement)

    if '__post_init__' in attrs:
        body.append(_post_init_call_codegen(attrs))

    code = "\n".join(body)

    return code, mini_fields_dict


def make_fast_init(
    attrs: typing.Dict[str, typing.Any],
) -> typing.Callable[[typing.Any], typing.Any]:
    body_code, cbs = _fast_init_body(attrs)
    statements = (_init_header(attrs), body_code)

    code = "\n".join(statements)

    local_ns = {}
    cbs["inspect"] = inspect
    cbs["process_validator_errors"] = process_validator_errors

    exec(code, cbs, local_ns)

    return local_ns["__init__"]
