from typing import Callable, List

from .typing import PreFormatType, ValidatorType


def validator(field_names: List[str]) -> Callable[[ValidatorType], ValidatorType]:
    """
    Decorator to mark a method as a validator for specified fields.
    Validators are collected and wired up at class creation time by SchemaMeta.

    Args:
        field_names: List of field names to apply the validator to

    Returns:
        The original function with metadata attached

    Example:
        @validator(['email'])
        def validate_email(self, value: str) -> bool:
            return '@' in value
    """

    def decorator(func: ValidatorType) -> ValidatorType:
        if not hasattr(func, "_validator_fields"):
            func._validator_fields = set()  # type: ignore[attr-defined]
        func._validator_fields.update(field_names)  # type: ignore[attr-defined]
        return func

    return decorator


def preformat(field_names: List[str]) -> Callable[[PreFormatType], PreFormatType]:
    """
    Decorator to mark a method as a preformatter for specified fields.
    Preformatters are collected and wired up at class creation time by SchemaMeta.

    Args:
        field_names: List of field names to apply the preformat callback to

    Returns:
        The original function with metadata attached

    Example:
        @preformat(['email', 'username'])
        def lowercase(self, value: str) -> str:
            return value.lower()
    """

    def decorator(func: PreFormatType) -> PreFormatType:
        if not hasattr(func, "_preformat_fields"):
            func._preformat_fields = set()  # type: ignore[attr-defined]
        func._preformat_fields.update(field_names)  # type: ignore[attr-defined]
        return func

    return decorator
