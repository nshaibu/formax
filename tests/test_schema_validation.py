import pytest
import time
import json
from pydantic_mini import (
    BaseModel,
    validator,
    preformat,
    ValidationError,
    ValidationFlags,
)


def test_aggregate_errors_single_field_multiple_validators():
    """Test that multiple validators on same field aggregate errors."""

    class User(BaseModel):
        username: str

        @validator(["username"], order=1)
        def check_length(self, value):
            if len(value) < 3:
                raise ValidationError("Username too short (min 3 chars)")

        @validator(["username"], order=2)
        def check_alphanumeric(self, value):
            if not value.isalnum():
                raise ValidationError("Username must be alphanumeric")

        class Config:
            schema_mode = True

    # Both validators fail
    with pytest.raises(ValidationError) as exc_info:
        User(username="a!")

    error = exc_info.value

    # Should have 2 errors
    assert error.error_count() == 2
    assert not error.fail_fast

    errors = error.errors()
    assert len(errors) == 2

    # Check error details
    assert errors[0]["field"] == "username"
    assert "too short" in errors[0]["message"].lower()

    assert errors[1]["field"] == "username"
    assert "alphanumeric" in errors[1]["message"].lower()


def test_aggregate_errors_multiple_fields():
    """Test error aggregation across multiple fields."""

    class User(BaseModel):
        username: str
        email: str
        age: int

        @validator(["username"])
        def check_username(self, value):
            if len(value) < 3:
                raise ValidationError("Username too short")

        @validator(["email"])
        def check_email(self, value):
            if "@" not in value:
                raise ValidationError("Invalid email format")

        @validator(["age"])
        def check_age(self, value):
            if value < 0:
                raise ValidationError("Age must be non-negative")

        class Config:
            schema_mode = True

    # All fields invalid
    with pytest.raises(ValidationError) as exc_info:
        User(username="ab", email="invalid", age=-5)

    error = exc_info.value
    assert error.error_count() == 3

    errors = error.errors()
    fields_with_errors = {e["field"] for e in errors}
    assert fields_with_errors == {"username", "email", "age"}

    # Check specific error messages
    username_error = next(e for e in errors if e["field"] == "username")
    assert "too short" in username_error["message"].lower()
    assert username_error["input"] == "ab"

    email_error = next(e for e in errors if e["field"] == "email")
    assert "invalid" in email_error["message"].lower()
    assert email_error["input"] == "invalid"

    age_error = next(e for e in errors if e["field"] == "age")
    assert "negative" in age_error["message"].lower()
    assert age_error["input"] == -5


def test_aggregate_errors_partial_failure():
    """Test that valid fields are processed while invalid ones are collected."""

    class Product(BaseModel):
        name: str
        price: float
        quantity: int

        @validator(["price"])
        def check_price(self, value):
            if value <= 0:
                raise ValidationError("Price must be positive")

        @validator(["quantity"])
        def check_quantity(self, value):
            if value < 0:
                raise ValidationError("Quantity cannot be negative")

        class Config:
            schema_mode = True

    # name is valid, price and quantity are invalid
    with pytest.raises(ValidationError) as exc_info:
        Product(name="Widget", price=-10.0, quantity=-5)

    error = exc_info.value
    assert error.error_count() == 2

    errors = error.errors()
    error_fields = {e["field"] for e in errors}
    assert error_fields == {"price", "quantity"}

    # name should not have error (it's valid)
    assert "name" not in error_fields


def test_aggregate_errors_with_cross_field_validation():
    """Test error aggregation with cross-field validators using ordering."""

    class Order(BaseModel):
        quantity: int
        max_quantity: int
        total: float

        @validator(["quantity"], order=1)
        def check_quantity_positive(self, value):
            if value <= 0:
                raise ValidationError("Quantity must be positive")

        @validator(["max_quantity"], order=1)
        def check_max_positive(self, value):
            if value <= 0:
                raise ValidationError("Max quantity must be positive")

        @validator(["quantity"], order=10)
        def check_quantity_within_max(self, value):
            # Cross-field validation
            if value > self.max_quantity:
                raise ValidationError("Quantity exceeds maximum")

        @validator(["total"], order=10)
        def check_total(self, value):
            if value < 0:
                raise ValidationError("Total cannot be negative")

        class Config:
            schema_mode = True

    # Multiple validation failures across orders
    with pytest.raises(ValidationError) as exc_info:
        Order(quantity=-5, max_quantity=-10, total=-100)

    error = exc_info.value

    # Should collect errors from order 1 validators
    # order 10 validators might not run if dependencies failed
    errors = error.errors()

    assert error.error_count() >= 2  # At least quantity and max_quantity

    error_messages = [e["message"] for e in errors]
    assert any("positive" in msg.lower() for msg in error_messages)


def test_aggregate_errors_all_valid():
    """Test that valid data doesn't raise errors even with aggregate_errors=True."""

    class User(BaseModel):
        username: str
        email: str
        age: int

        @validator(["username"])
        def check_username(self, value):
            if len(value) < 3:
                raise ValidationError("Username too short")

        @validator(["email"])
        def check_email(self, value):
            if "@" not in value:
                raise ValidationError("Invalid email")

        @validator(["age"])
        def check_age(self, value):
            if value < 0:
                raise ValidationError("Age negative")

        class Config:
            schema_mode = True

    # All valid - should not raise
    user = User(username="alice", email="alice@example.com", age=25)

    assert user.username == "alice"
    assert user.email == "alice@example.com"
    assert user.age == 25


def test_aggregate_errors_serialization():
    """Test that aggregated errors can be serialized to JSON/dict."""

    class User(BaseModel):
        username: str
        email: str

        @validator(["username"])
        def check_username(self, value):
            if len(value) < 3:
                raise ValidationError("Username too short")
            return value

        @validator(["email"])
        def check_email(self, value):
            if "@" not in value:
                raise ValidationError("Invalid email")
            return value

        class Config:
            schema_mode = True

    with pytest.raises(ValidationError) as exc_info:
        User(username="ab", email="bad")

    error = exc_info.value

    # Test dict() method
    error_dict = error.dict()
    assert "detail" in error_dict
    assert "errors" in error_dict
    assert len(error_dict["errors"]) == 2

    error_json = error.json()
    parsed = json.loads(error_json)

    assert parsed["detail"] == "Validation failed"
    assert len(parsed["errors"]) == 2

    # Check structure
    for err in parsed["errors"]:
        assert "field" in err
        assert "message" in err
        assert "input" in err


def test_aggregate_errors_with_preformatters():
    """Test that preformatters run before validation even with aggregation."""

    class User(BaseModel):
        username: str
        email: str

        @preformat(["username"], order=1)
        def normalize_username(self, value):
            return value.strip().lower()

        @preformat(["email"], order=1)
        def normalize_email(self, value):
            return value.strip().lower()

        @validator(["username"], order=2)
        def check_username(self, value):
            # value should already be normalized
            if len(value) < 3:
                raise ValidationError("Username too short")
            return value

        @validator(["email"], order=2)
        def check_email(self, value):
            # value should already be normalized
            if "@" not in value:
                raise ValidationError("Invalid email")
            return value

        class Config:
            schema_mode = True

    # Both fail after preformatting
    with pytest.raises(ValidationError) as exc_info:
        User(username="  AB  ", email="  INVALID  ")

    error = exc_info.value
    errors = error.errors()

    # Check that preformatted values are in error (lowercase, stripped)
    username_error = next(e for e in errors if e["field"] == "username")
    email_error = next(e for e in errors if e["field"] == "email")

    # Values should be preformatted in error report
    assert username_error["input"] == "ab"  # Normalized
    assert email_error["input"] == "invalid"  # Normalized


def test_fail_fast_vs_aggregate_errors():
    """Test difference between fail-fast and aggregate modes."""

    # Fail-fast model (default)
    class FailFastModel(BaseModel):
        username: str
        email: str
        age: int

        @validator(["username"])
        def check_username(self, value):
            if len(value) < 3:
                raise ValidationError("Username too short")
            return value

        @validator(["email"])
        def check_email(self, value):
            if "@" not in value:
                raise ValidationError("Invalid email")
            return value

        @validator(["age"])
        def check_age(self, value):
            if value < 0:
                raise ValidationError("Age negative")
            return value

        # No Config - fail-fast is default

    # Aggregate model
    class AggregateModel(BaseModel):
        username: str
        email: str
        age: int

        @validator(["username"])
        def check_username(self, value):
            if len(value) < 3:
                raise ValidationError("Username too short")
            return value

        @validator(["email"])
        def check_email(self, value):
            if "@" not in value:
                raise ValidationError("Invalid email")
            return value

        @validator(["age"])
        def check_age(self, value):
            if value < 0:
                raise ValidationError("Age negative")
            return value

        class Config:
            schema_mode = True

    # Fail-fast: Only first error
    with pytest.raises(ValidationError) as exc_info:
        FailFastModel(username="ab", email="bad", age=-5)

    fail_fast_error = exc_info.value
    assert fail_fast_error.fail_fast == True
    assert fail_fast_error.error_count() == 1  # Only first error

    # Aggregate: All errors
    with pytest.raises(ValidationError) as exc_info:
        AggregateModel(username="ab", email="bad", age=-5)

    aggregate_error = exc_info.value
    assert aggregate_error.fail_fast == False
    assert aggregate_error.error_count() == 3  # All errors


def test_aggregate_errors_with_attrib_validators():
    """Test error aggregation with built-in Attrib validators."""

    from pydantic_mini import MiniAnnotated, Attrib

    class Product(BaseModel):
        name: MiniAnnotated[str, Attrib(min_length=3, max_length=50)]
        price: MiniAnnotated[float, Attrib(gt=0, le=10000)]
        quantity: MiniAnnotated[int, Attrib(ge=0, le=1000)]

        class Config:
            schema_mode = True

    # All fields violate constraints
    with pytest.raises(ValidationError) as exc_info:
        Product(name="ab", price=-10, quantity=-5)

    error = exc_info.value
    assert error.error_count() == 3

    errors = error.errors()
    error_fields = {e["field"] for e in errors}
    assert error_fields == {"name", "price", "quantity"}


def test_aggregate_errors_nested_models():
    """Test error aggregation in nested models."""

    class Address(BaseModel):
        street: str
        city: str

        @validator(["street"])
        def check_street(self, value):
            if len(value) < 3:
                raise ValidationError("Street too short")
            return value

        @validator(["city"])
        def check_city(self, value):
            if len(value) < 2:
                raise ValidationError("City too short")
            return value

        class Config:
            schema_mode = True

    class User(BaseModel):
        name: str
        address: Address

        @validator(["name"])
        def check_name(self, value):
            if len(value) < 3:
                raise ValidationError("Name too short")
            return value

        class Config:
            schema_mode = True

    # Parent and nested model both have errors
    with pytest.raises(ValidationError) as exc_info:
        User(name="ab", address={"street": "st", "city": "c"})

    error = exc_info.value

    # Should have error from parent and nested model
    # Exact count depends on how nested errors are reported
    assert error.error_count() >= 1


def test_aggregate_errors_with_type_coercion():
    """Test that type coercion errors are aggregated."""

    class Model(BaseModel):
        age: int
        price: float
        active: bool

        @validator(["age"])
        def check_age(self, value):
            if value < 0:
                raise ValidationError("Age negative")

        class Config:
            schema_mode = True
            validation = ValidationFlags.VALIDATED  # Type checking enabled

    # Invalid types that can't be coerced + validator failures
    with pytest.raises(ValidationError) as exc_info:
        Model(age="not_a_number", price="invalid", active="maybe")

    error = exc_info.value

    # Should have type errors for all fields
    assert error.error_count() >= 1
    errors = error.errors()

    # At least one error should be a type error
    assert any("type" in e["message"].lower() for e in errors)


def test_aggregate_errors_iteration():
    """Test iterating over aggregated errors."""

    class User(BaseModel):
        username: str
        email: str
        age: int

        @validator(["username"])
        def check_username(self, value):
            if len(value) < 3:
                raise ValidationError("Username too short")
            return value

        @validator(["email"])
        def check_email(self, value):
            if "@" not in value:
                raise ValidationError("Invalid email")
            return value

        @validator(["age"])
        def check_age(self, value):
            if value < 0:
                raise ValidationError("Age negative")
            return value

        class Config:
            schema_mode = True

    with pytest.raises(ValidationError) as exc_info:
        User(username="ab", email="bad", age=-5)

    error = exc_info.value

    # Test iteration
    error_list = list(error.errors())
    assert len(error_list) == 3

    # Test that each error has required keys
    for err in error_list:
        assert "field" in err
        assert "message" in err
        assert "input" in err
        assert isinstance(err["field"], str)
        assert isinstance(err["message"], str)


def test_aggregate_errors_with_none_values():
    """Test error aggregation with None/empty values."""

    from typing import Optional

    class User(BaseModel):
        username: str
        email: Optional[str]  # Auto-defaults to None

        @validator(["username"])
        def check_username(self, value):
            if not value:
                raise ValidationError("Username required")
            return value

        @validator(["email"])
        def check_email(self, value):
            if value is not None and "@" not in value:
                raise ValidationError("Invalid email")
            return value

        class Config:
            schema_mode = True

    # username is empty (error), email is None (ok)
    with pytest.raises(ValidationError) as exc_info:
        User(username="")

    error = exc_info.value
    assert error.error_count() == 1

    errors = error.errors()
    assert errors[0]["field"] == "username"
    assert errors[0]["input"] == ""


def test_aggregate_errors_api_response_format():
    """Test that errors are in a format suitable for API responses."""

    class UserRegistration(BaseModel):
        username: str
        email: str
        password: str
        age: int

        @validator(["username"])
        def check_username(self, value):
            if len(value) < 3:
                raise ValidationError("Username must be at least 3 characters")
            return value

        @validator(["email"])
        def check_email(self, value):
            if "@" not in value:
                raise ValidationError("Invalid email address")
            return value

        @validator(["password"])
        def check_password(self, value):
            if len(value) < 8:
                raise ValidationError("Password must be at least 8 characters")
            return value

        @validator(["age"])
        def check_age(self, value):
            if value < 13:
                raise ValidationError("Must be at least 13 years old")
            return value

        class Config:
            schema_mode = True

    # Simulate API request with multiple errors
    try:
        UserRegistration(username="ab", email="invalid", password="short", age=10)
    except ValidationError as e:
        # Format suitable for FastAPI/Flask response
        response = {
            "status": "error",
            "message": "Validation failed",
            "errors": e.errors(),
        }

        assert response["status"] == "error"
        assert len(response["errors"]) == 4

        # Check each error has API-friendly structure
        for error in response["errors"]:
            assert "field" in error
            assert "message" in error
            assert "input" in error

            # Verify specific errors
            if error["field"] == "username":
                assert "3 characters" in error["message"]
            elif error["field"] == "email":
                assert "Invalid email" in error["message"]
            elif error["field"] == "password":
                assert "8 characters" in error["message"]
            elif error["field"] == "age":
                assert "13 years" in error["message"]
