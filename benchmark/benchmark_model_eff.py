import json
from .models import (
    UserDC,
    UserMini,
    UserNestedDC,
    UserNestedMini,
    ProfileDC,
)


def test_flat_dataclass(benchmark, data):
    benchmark(lambda: UserDC(**data))


def test_flat_pydantic_mini(benchmark, data):
    benchmark(lambda: UserMini(**data))


def test_nested_dataclass(benchmark, nested_data):
    benchmark(
        lambda: UserNestedDC(
            id=nested_data["id"],
            name=nested_data["name"],
            profile=ProfileDC(**nested_data["profile"]),
        )
    )


def test_nested_pydantic_mini(benchmark, nested_data):
    benchmark(lambda: UserNestedMini(**nested_data))


def test_pydantic_mini_json(benchmark, json_data):
    benchmark(lambda: UserMini.loads(json_data, _format="json"))
