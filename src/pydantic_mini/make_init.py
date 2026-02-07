import typing
from dataclasses import MISSING

from .fields import MiniField
from .utils import make_private_field


def join_string(str_list: typing.List[str], sep: str = ",") -> str:
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

    default_params_str = join_string(default_params)
    params_str = join_string(params)

    return f"def __init__(self, {params_str} {default_params_str[:-1]}):"


def _post_init_codegen(attrs: typing.Dict[str, typing.Any]) -> str:
    pass


def _disable_all_validation_init_body(
    attrs: typing.Dict[str, typing.Any],
) -> typing.Tuple[str, typing.Dict[str, typing.Any]]:
    body = []
    cbs = {}

    field_names = list(attrs.get("__annotations__", []))

    for field_name in field_names:
        cb_statement = ""
        mini_field: typing.Optional[MiniField] = attrs.get(field_name)
        if mini_field and mini_field._preformat_callback:
            cb_name = f"preformat_{field_name}"
            cbs[cb_name] = mini_field._preformat_callback
            cb_statement = f"\t{field_name} = {cb_name}(self, {field_name})\n"

        private_name = make_private_field(field_name)
        statement = cb_statement + f"\tself.__dict__[{private_name!r}]={field_name}"
        body.append(statement)

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
    attrs: typing.Dict[str, typing.Any],
) -> typing.Tuple[str, typing.Dict[str, typing.Any]]:
    body = []
    preformat_cbs = {}
    validator_cbs = {}
    validator_queries = {}

    field_names = list(attrs.get("__annotations__", []))

    for field_name in field_names:
        cb_statement = ""
        validator_cbs_statement = ""
        query_validator_cbs_statement = ""

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

            query_name = f"validator_query_{field_name}"
            validator_queries[query_name] = mini_field._query
            query_validator_cbs_statement = (
                f"\t{query_name}.validate({field_name}, {field_name!r})\n"
            )

        private_name = make_private_field(field_name)
        statement = (
            cb_statement
            + query_validator_cbs_statement
            + validator_cbs_statement
            + f"\tself.__dict__[{private_name!r}]={field_name}"
        )
        body.append(statement)

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
    attrs: typing.Dict[str, typing.Any],
) -> typing.Tuple[str, typing.Dict[str, typing.Any]]:
    body = []
    mini_fields_dict = {}

    field_names = list(attrs.get("__annotations__", []))

    for field_name in field_names:
        mini_statement = ""

        mini_field: typing.Optional[MiniField] = attrs.get(field_name)

        if mini_field:
            mini_field_name = f"mini_field_{field_name}"
            mini_fields_dict[mini_field_name] = mini_field

            mini_statement = f"\tcoerced_{field_name}_value = {mini_field_name}.run_preformatters(self, {field_name})\n"

            if mini_field.__class__ == MiniField:
                # Resolve and set model context
                mini_statement += f"\tmodel_context_{field_name} = {mini_field_name}.get_model_context(self)\n"
                mini_statement += f"\t{mini_field_name}.expected_type.module_context = model_context_{field_name}\n"
                mini_statement += f"\tif {mini_field_name}.inner_type:\n"
                mini_statement += f"\t\t{mini_field_name}.inner_type.module_context = model_context_{field_name}\n\n"

                # Initialised type resolver
                mini_statement += f"\t{mini_field_name}._finalise_type_resolver()\n\n"

                # condition for coercing values
                mini_statement += f"\tcoerced_{field_name} = {mini_field_name}._value_coerce(coerced_{field_name}_value)\n"
                mini_statement += f"\tif coerced_{field_name} is not None:\n"
                mini_statement += (
                    f"\t\tcoerced_{field_name}_value = coerced_{field_name}\n\n"
                )

                # validate value
                mini_statement += f"\t{mini_field_name}._field_type_validator(coerced_{field_name}_value)\n"
            else:
                # for when a field is annotated with typing.Any
                mini_statement += f"\t{mini_field_name}._query.validate(coerced_{field_name}_value, {field_name!r})\n"

            mini_statement += f"\t{mini_field_name}.run_validators(self, coerced_{field_name}_value)\n\n"

        private_name = make_private_field(field_name)
        mini_statement += (
            f"\tself.__dict__[{private_name!r}]=coerced_{field_name}_value\n"
        )
        body.append(mini_statement)

    code = "\n".join(body)

    return code, mini_fields_dict


def make_fast_init(
    attrs: typing.Dict[str, typing.Any],
) -> typing.Callable[[typing.Any], typing.Any]:
    body_code, cbs = _fast_init_body(attrs)
    statements = (_init_header(attrs), body_code)

    code = "\n".join(statements)

    local_ns = {}

    exec(code, cbs, local_ns)

    return local_ns["__init__"]
