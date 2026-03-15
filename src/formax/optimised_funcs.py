from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .base import BaseModel

__all__ = [
    "NoCoercionMixin",
]


class NoCoercionMixin:
    def __set__(self, instance: "BaseModel", value: Any) -> None:
        value = self.processor_default_value(value)
        value = self.run_preformatters(instance, value)

        self.config_forward_ref(instance)

        self.field_type_validator(instance, value)
        self.run_validators(instance, value)

        instance.__dict__[self.private_name] = value
        return None
