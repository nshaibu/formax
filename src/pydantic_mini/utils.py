PRIVATE_FIELD_PREFIX = "_pydantic_mini_"

PYDANTIC_MINI_MODEL_CONFIG = "__pydantic_mini_model_config__"

PYDANTIC_MINI_SIGNATURE_MATCHER = "__pydantic_mini_signature_matcher__"

PYDANTIC_MINI_MODEL_CONTEXT = "__pydantic_mini_model_context__"

_DATACLASS_CONFIG_PARAMS = "__dataclass_params__"


def make_private_field(field_name):
    return f"{PRIVATE_FIELD_PREFIX}{field_name}"
