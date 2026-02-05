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