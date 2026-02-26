from typing import Callable, List

from .typing import PreFormatType, ValidatorType


def validator(
    field_names: List[str], order: int = 0
) -> Callable[[ValidatorType], ValidatorType]:
    """
    Decorator to mark a method as a validator for specified fields.
    Validators are collected and wired up at class creation time by SchemaMeta.

    Ordering Convention:
        - Order 0-9: Individual field validation
            @validator('field', order=0) # Default, no dependencies

        - Order 10-19: Cross-field validation (same object)
            @validator('field', order=10) # Depends on other fields

        - Order 20-29: Derived/computed field validation
            @validator('total', order=20) # Depends on validated fields

        - Order 30+: Complex business logic
            @validator('field', order=30) # Complex dependencies

        - Negative orders: Pre-validation normalization
            @validator('field', order=-10) # Run before everything

    Args:
        field_names: List of field names to apply the validator to
        order: Execution order (default 0)
               - Lower numbers run first
               - Same order: execution undefined within group
               - Negative orders allowed

    Returns:
        The original function with metadata attached

    Example:
        >>> @validator(['email'])
        >>> def validate_email(self, value: str) -> bool:
        >>>    return '@' in value
    """

    def decorator(func: ValidatorType) -> ValidatorType:
        if not hasattr(func, "_validator_fields"):
            func._validator_fields = set()  # type: ignore[attr-defined]
        func._validator_fields.update(field_names)  # type: ignore[attr-defined]
        func._validator_order = order
        return func

    return decorator


def preformat(
    field_names: List[str], order: int = 0
) -> Callable[[PreFormatType], PreFormatType]:
    """
    Decorator to mark a method as a preformatter for specified fields.
    Preformatters are collected and wired up at class creation time by SchemaMeta.

    Ordering Convention:
        - Order 0-9: Individual field validation
            @validator('field', order=0) # Default, no dependencies

        - Order 10-19: Cross-field validation (same object)
            @validator('field', order=10) # Depends on other fields

        - Order 20-29: Derived/computed field validation
            @validator('total', order=20) # Depends on validated fields

        - Order 30+: Complex business logic
            @validator('field', order=30) # Complex dependencies

        - Negative orders: Pre-validation normalization
            @validator('field', order=-10) # Run before everything

    Args:
        field_names: List of field names to apply the preformat callback to
        order: Execution order (default 0)
               - Lower numbers run first
               - Same order: execution undefined within group
               - Negative orders allowed

    Returns:
        The original function with metadata attached

    Example:
        >>> @preformat(['email', 'username'], order=0)
        >>> def lowercase(self, value: str) -> str:
        >>>    return value.lower()
    """

    def decorator(func: PreFormatType) -> PreFormatType:
        if not hasattr(func, "_preformat_fields"):
            func._preformat_fields = set()  # type: ignore[attr-defined]
        func._preformat_fields.update(field_names)  # type: ignore[attr-defined]
        func._preformat_order = order
        return func

    return decorator


def postformat(
    field_names: List[str], order: int = 0
) -> Callable[[PreFormatType], PreFormatType]:
    """
    Decorator to mark a method as a preformatter for specified fields.
    Preformatters are collected and wired up at class creation time by SchemaMeta.

    Ordering Convention:
        - Order 0-9: Individual field validation
            @validator('field', order=0) # Default, no dependencies

        - Order 10-19: Cross-field validation (same object)
            @validator('field', order=10) # Depends on other fields

        - Order 20-29: Derived/computed field validation
            @validator('total', order=20) # Depends on validated fields

        - Order 30+: Complex business logic
            @validator('field', order=30) # Complex dependencies

        - Negative orders: Pre-validation normalization
            @validator('field', order=-10) # Run before everything

    Args:
        field_names: List of field names to apply the postformat callback to
        order: Execution order (default 0)
               - Lower numbers run first
               - Same order: execution undefined within group
               - Negative orders allowed

    Returns:
        The original function with metadata attached

    Example:
        >>> @postformat(['email', 'username'], order=0)
        >>> def lowercase(self, value: str) -> str:
        >>>    return value.lower()
    """

    def decorator(func: PreFormatType) -> PreFormatType:
        if not hasattr(func, "_postformat_fields"):
            func._postformat_fields = set()  # type: ignore[attr-defined]
        func._postformat_fields.update(field_names)  # type: ignore[attr-defined]
        func._postformat_order = order
        return func

    return decorator
