import gc
import json
import tracemalloc

from .models import (
    UserDC,
    UserMini,
    UserNestedDC,
    UserNestedMini,
    ProfileDC,
)


def measure_peak(fn, rounds=10_000):
    gc.collect()
    tracemalloc.start()

    for _ in range(rounds):
        fn()

    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return peak


def test_memory_flat_models(data):
    print("\nFlat model peak memory (bytes)")
    print("dataclass     :", measure_peak(lambda: UserDC(**data)))
    print("pydantic-mini :", measure_peak(lambda: UserMini(**data)))


def test_memory_nested_models(nested_data):
    print("\nNested model peak memory (bytes)")
    print(
        "dataclass     :",
        measure_peak(
            lambda: UserNestedDC(
                id=nested_data["id"],
                name=nested_data["name"],
                profile=ProfileDC(**nested_data["profile"]),
            )
        ),
    )
    print("pydantic-mini :", measure_peak(lambda: UserNestedMini(**nested_data)))


def test_memory_json(data):
    json_data = json.dumps(data)

    print("\nJSON parsing peak memory (bytes)")
    print(
        "pydantic-mini :",
        measure_peak(lambda: UserMini.loads(json_data, _format="json")),
    )
