import json
from .models import (
    UserDC,
    UserMini,
    UserNestedDC,
    UserNestedMini,
    ProfileDC,
    UserPyd,
    UserNestedPyd,
    DisableTypeCheckMini,
    DisableAllValidationMini,
    FlatDisableTypeCheckProfileMini,
    FlatDisableAllValidationProfileMini,
)


def test_flat_dataclass(benchmark, data):
    benchmark(lambda: UserDC(**data))


def test_flat_formax(benchmark, data):
    benchmark(lambda: UserMini(**data))


def test_nested_dataclass(benchmark, nested_data):
    benchmark(
        lambda: UserNestedDC(
            id=nested_data["id"],
            name=nested_data["name"],
            profile=ProfileDC(**nested_data["profile"]),
        )
    )


def test_nested_formax(benchmark, nested_data):
    benchmark(lambda: UserNestedMini(**nested_data))


def test_nested_disable_all_validation_formax(benchmark, nested_data):
    benchmark(lambda: DisableAllValidationMini(**nested_data))


def test_nested_disable_type_check_formax(benchmark, nested_data):
    benchmark(lambda: DisableTypeCheckMini(**nested_data))


def test_flat_disable_all_validation_formax(benchmark, data):
    benchmark(lambda: FlatDisableAllValidationProfileMini(**data))


def test_flat_disable_type_check_formax(benchmark, data):
    benchmark(lambda: FlatDisableTypeCheckProfileMini(**data))


def test_formax_json(benchmark, json_data):
    benchmark(lambda: UserMini.loads(json_data, _format="json"))


def test_flat_pydantic(benchmark, data):
    benchmark(lambda: UserPyd(**data))


def test_nested_pydantic(benchmark, nested_data):
    benchmark(lambda: UserNestedPyd(**nested_data))


def test_pydantic_json(benchmark, json_data):
    benchmark(lambda: UserPyd.model_validate_json(json_data))
