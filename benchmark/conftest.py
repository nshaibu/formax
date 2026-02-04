import pytest
from .models import DATA, NESTED_DATA, JSON_DATA


@pytest.fixture(scope="session")
def data():
    return DATA


@pytest.fixture(scope="session")
def nested_data():
    return NESTED_DATA


@pytest.fixture(scope="session")
def json_data():
    return JSON_DATA
