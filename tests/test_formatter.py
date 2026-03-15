import pytest
import json
import typing
from formax import BaseModel, MiniAnnotated, Attrib
from formax.formatters import (
    DictModelFormatter,
    JSONModelFormatter,
    CSVModelFormatter,
)


class User(BaseModel):
    id: int
    username: str


class Post(BaseModel):
    title: str
    author: MiniAnnotated[User, Attrib()]


class Skill(BaseModel):
    name: str
    level: int


class Developer(BaseModel):
    name: str
    skills: MiniAnnotated[typing.List[Skill], Attrib(default_factory=list)]


class InventoryItem(BaseModel):
    id: int
    name: str
    quantity: int


def test_dict_formatter_single_encode():
    """Test encoding a single dict into a BaseModel instance."""
    formatter = DictModelFormatter()
    data = {"id": 1, "username": "dev_user"}

    user = formatter.encode(User, data)

    assert isinstance(user, User)
    assert user.id == 1
    assert user.username == "dev_user"


def test_dict_formatter_list_encode():
    formatter = DictModelFormatter()
    data = [{"id": 1, "username": "alice"}, {"id": 2, "username": "bob"}]

    users = formatter.encode(User, data)

    assert isinstance(users, list)
    assert len(users) == 2
    assert all(isinstance(u, User) for u in users)
    assert users[1].username == "bob"


def test_dict_formatter_nested_encode():
    formatter = DictModelFormatter()
    data = {
        "title": "Hello Pydantic Mini",
        "author": {"id": 99, "username": "nathaniel"},
    }

    post = formatter.encode(Post, data)

    assert isinstance(post, Post)
    assert isinstance(post.author, User)
    assert post.author.username == "nathaniel"


def test_dict_formatter_decode_asdict():
    formatter = DictModelFormatter()
    user_obj = User(id=10, username="tester")

    result = formatter.decode(user_obj)

    assert isinstance(result, dict)
    assert result["id"] == 10
    assert result["username"] == "tester"


def test_dict_formatter_list_decode():
    formatter = DictModelFormatter()
    instances = [User(id=1, username="u1"), User(id=2, username="u2")]

    result = formatter.decode(instances)

    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["username"] == "u1"


def test_dict_formatter_invalid_input():
    formatter = DictModelFormatter()
    with pytest.raises(TypeError, match="Object must be dict or list"):
        formatter.encode(User, "just a string")


def test_json_encode_single():
    """Test encoding a JSON string into a single BaseModel instance."""
    formatter = JSONModelFormatter()
    json_data = '{"name": "Alice", "skills": [{"name": "Python", "level": 10}]}'

    dev = formatter.encode(Developer, json_data)

    assert isinstance(dev, Developer)
    assert dev.name == "Alice"
    assert isinstance(dev.skills[0], Skill)
    assert dev.skills[0].name == "Python"


def test_json_encode_list():
    formatter = JSONModelFormatter()
    json_data = '[{"name": "Alice", "level": 10}, {"name": "Bob", "level": 8}]'

    skills = formatter.encode(Skill, json_data)

    assert isinstance(skills, list)
    assert len(skills) == 2
    assert skills[1].name == "Bob"


def test_json_decode_single():
    formatter = JSONModelFormatter()
    dev = Developer(name="Charlie", skills=[Skill(name="Go", level=7)])

    json_str = formatter.decode(dev)

    # Parse it back to verify content
    data = json.loads(json_str)
    assert data["name"] == "Charlie"
    assert data["skills"][0]["name"] == "Go"
    assert isinstance(json_str, str)


def test_json_decode_list():
    formatter = JSONModelFormatter()
    skills = [Skill(name="AI", level=9), Skill(name="ML", level=8)]

    json_str = formatter.decode(skills)
    data = json.loads(json_str)

    assert isinstance(data, list)
    assert data[0]["name"] == "AI"
    assert '"name": "ML"' in json_str


def test_json_invalid_format():
    formatter = JSONModelFormatter()
    bad_json = '{"name": "Broken" '  # Missing closing brace

    with pytest.raises(json.JSONDecodeError):
        formatter.encode(Developer, bad_json)


def test_csv_decode_to_string():
    formatter = CSVModelFormatter()
    items = [
        InventoryItem(id=1, name="Widget", quantity=100),
        InventoryItem(id=2, name="Gadget", quantity=50),
    ]

    csv_output = formatter.decode(items)

    # Check if header and rows are present
    assert "id,name,quantity" in csv_output
    assert "1,Widget,100" in csv_output
    assert "2,Gadget,50" in csv_output


def test_csv_single_instance_decode():
    formatter = CSVModelFormatter()
    item = InventoryItem(id=1, name="Solo", quantity=1)

    csv_output = formatter.decode(item)
    lines = csv_output.strip().split("\n")

    assert len(lines) == 2  # Header + 1 Row
    assert lines[1].startswith("1,Solo,1")
