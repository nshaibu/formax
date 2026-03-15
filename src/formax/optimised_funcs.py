from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .base import BaseModel

__all__ = [
    "full_setter_no_coercion",
    "scalar_full_no_config_ref",
    "collection_full_no_config_ref",
]


def full_setter_no_coercion(self, instance: "BaseModel", value: Any) -> None:
    value = self.processor_default_value(value)
    value = self.run_preformatters(instance, value)

    self._config_forward_ref(instance)

    self.field_type_validator(instance, value)
    self.run_validators(instance, value)

    instance.__dict__[self.private_name] = value
    return None


def scalar_full_no_config_ref(self, instance: "BaseModel") -> None:
    self.expected_type._finalised = True


def collection_full_no_config_ref(self, instance: "BaseModel") -> None:
    self.expected_type._finalised = True
    self.inner_type._finalised = True
