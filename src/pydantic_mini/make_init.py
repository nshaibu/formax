import typing
from dataclasses import MISSING

from .fields import MiniField
from .utils import make_private_field


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

    default_params_str = ", ".join(default_params)
    params_str = ", ".join(params)

    return f"def __init__(self, {params_str}, {default_params_str}):"


def _disable_all_validation_init_body(
    attrs: typing.Dict[str, typing.Any],
) -> typing.Tuple[str, typing.Dict[str, typing.Any]]:
    body = []
    cbs = {}

    field_names = list(attrs.get("__annotations__", []))

    # Validate no extra kwargs
    if field_names:
        body.append(f"\texpected = {set(field_names)!r}")
        body.append("\tprovided = set(locals().keys()) - {'self', 'expected'}")
        body.append("\textra = provided - expected")
        body.append("\tif extra:")
        body.append("\t\traise TypeError(f'Unexpected keyword arguments: {extra}')")
        body.append("")  # Blank line for readability

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
