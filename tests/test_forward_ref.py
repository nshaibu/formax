import pytest
from typing import Optional, List
from formax import BaseModel, MiniAnnotated, Attrib


class TaskNode(BaseModel):
    name: str
    child: Optional["TaskNode"]


class Folder(BaseModel):
    name: str
    contents: MiniAnnotated[List["Folder"], Attrib(default_factory=list)]


class Parent(BaseModel):
    name: str
    first_born: Optional["Child"]


class Child(BaseModel):
    age: int


def test_self_reference_inflation():
    data = {
        "name": "Root",
        "child": {"name": "Level 1", "child": {"name": "Level 2", "child": None}},
    }

    root = TaskNode.loads(data, _format="dict")

    assert isinstance(root, TaskNode)
    assert isinstance(root.child, TaskNode)
    assert isinstance(root.child.child, TaskNode)

    assert root.name == "Root"
    assert root.child.name == "Level 1"
    assert root.child.child.name == "Level 2"
    assert root.child.child.child is None


def test_forward_reference_resolution():
    data = {"name": "John Doe", "first_born": {"age": 10}}

    parent = Parent.loads(data, _format="dict")

    assert isinstance(parent, Parent)
    assert isinstance(parent.first_born, Child)
    assert parent.first_born.age == 10


def test_recursive_list_inflation():
    data = {
        "name": "Home",
        "contents": [
            {"name": "Documents", "contents": []},
            {"name": "Pictures", "contents": [{"name": "Vacation", "contents": []}]},
        ],
    }

    home = Folder.loads(data, _format="dict")

    assert len(home.contents) == 2
    assert isinstance(home.contents[0], Folder)
    assert isinstance(home.contents[1].contents[0], Folder)
    assert home.contents[1].contents[0].name == "Vacation"
