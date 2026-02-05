import pytest
from pydantic_mini import BaseModel, validator, preformat
from pydantic_mini.exceptions import ValidationError


def test_single_field_validator():
    class Model(BaseModel):
        age: int

        @validator(['age'])
        def check_age(self, value):
            if value < 0:
                raise ValidationError("Must be positive")

    m = Model(age=25)
    assert m.age == 25

    with pytest.raises(ValidationError):
        Model(age=-5)


def test_multi_field_validator():
    class Model(BaseModel):
        field_a: int
        field_b: int

        @validator(['field_a', 'field_b'])
        def check_both(self, value):
            if value < 0:
                raise ValidationError("Must be positive")

    m = Model(field_a=1, field_b=2)

    with pytest.raises(ValidationError):
        Model(field_a=-1, field_b=2)


def test_instance_access_in_validator():
    class Model(BaseModel):
        min_val: int
        max_val: int

        @validator(['max_val'])
        def check_max(self, value):
            if value <= self.min_val:
                raise ValidationError("max must be > min")

    m = Model(min_val=10, max_val=20)

    with pytest.raises(ValidationError):
        Model(min_val=10, max_val=5)


def test_single_field_preformatter():
    class Model(BaseModel):
        age: int

        @preformat(['age'])
        def check_age(self, value):
            return value + 5

    m = Model(age=25)
    assert m.age == 30


def test_validator_with_typing_any():
    """Test validators skip for typing.Any fields."""
    import typing

    class Model(BaseModel):
        validated: int
        flexible: typing.Any = None

        @validator(['validated'])
        def check_validated(self, value):
            if value < 0:
                raise ValidationError("Must be positive")

        @validator(['flexible'])
        def this_should_not_run(self, value):
            # Should be skipped
            raise ValidationError("Should not reach here")


    m = Model(validated=10, flexible="anything")
    assert m.flexible == "anything"


def test_nested_model_validation():
    """Test validators work with nested models."""

    class Inner(BaseModel):
        value: int

        @validator(['value'])
        def check_value(self, value):
            if value < 0:
                raise ValidationError("Must be positive")

    class Outer(BaseModel):
        inner: Inner

    Outer(inner={"value": 10})  # OK

    with pytest.raises(ValidationError):
        Outer(inner={"value": -5})


def test_validator_error_messages():
    class Model(BaseModel):
        age: int

        @validator(['age'])
        def check_age(self, value):
            if value < 0:
                raise ValidationError("Age cannot be negative")
            if value > 150:
                raise ValidationError("Age too high")

    with pytest.raises(ValidationError, match="Age cannot be negative"):
        Model(age=-5)

    with pytest.raises(ValidationError, match="Age too high"):
        Model(age=200)


def test_cross_field_validation():
    class Model(BaseModel):
        min_val: int
        max_val: int

        @validator(['max_val'])
        def check_max(self, value):
            if value <= self.min_val:
                raise ValidationError("max must be > min")

    Model(min_val=10, max_val=20)  # OK
    with pytest.raises(ValidationError):
        Model(min_val=20, max_val=10)