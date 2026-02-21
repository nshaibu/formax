import json
from dataclasses import dataclass
from typing import List

try:
    from pydantic import BaseModel as PydanticBaseModel
except ImportError:
    PydanticBaseModel = object

from pydantic_mini import BaseModel, ValidationFlags


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

    # class Config:
    #     frozen = True


class DisableAllValidationMini(BaseModel):
    id: int
    name: str
    profile: ProfileMini

    class Config:
        validation = ValidationFlags.NONE


class DisableTypeCheckMini(BaseModel):
    id: int
    name: str
    profile: ProfileMini

    class Config:
        validation = ValidationFlags.COERCE


class FlatDisableAllValidationProfileMini(BaseModel):
    id: int
    name: str
    scores: List[int]
    active: bool

    class Config:
        # frozen = True
        validation = ValidationFlags.NONE


class FlatDisableTypeCheckProfileMini(BaseModel):
    id: int
    name: str
    scores: List[int]
    active: bool

    class Config:
        # frozen = True
        validation = ValidationFlags.COERCE


# ----------------------------
# Pydantic v2
# ----------------------------
class ProfilePyd(PydanticBaseModel):
    email: str
    age: int


class UserPyd(PydanticBaseModel):
    id: int
    name: str
    scores: List[int]
    active: bool


class UserNestedPyd(PydanticBaseModel):
    id: int
    name: str
    profile: ProfilePyd
