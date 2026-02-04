import json
from dataclasses import dataclass
from typing import List

from pydantic_mini import BaseModel


DATA = {
    "id": 123,
    "name": "Alice",
    "scores": [10, 20, 30],
    "active": True,
}

NESTED_DATA = {
    "id": 123,
    "name": "Alice",
    "profile": {
        "email": "alice@example.com",
        "age": 30,
    },
}

JSON_DATA = json.dumps(DATA)


@dataclass
class ProfileDC:
    email: str
    age: int


@dataclass
class UserDC:
    id: int
    name: str
    scores: List[int]
    active: bool


@dataclass
class UserNestedDC:
    id: int
    name: str
    profile: ProfileDC


class ProfileMini(BaseModel):
    email: str
    age: int


class UserMini(BaseModel):
    id: int
    name: str
    scores: List[int]
    active: bool


class UserNestedMini(BaseModel):
    id: int
    name: str
    profile: ProfileMini
