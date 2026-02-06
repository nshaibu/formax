PRIVATE_FIELD_PREFIX = "_pydantic_mini_"


def make_private_field(field_name):
    return f"{PRIVATE_FIELD_PREFIX}{field_name}"
