from pydantic_mini import BaseModel, validator, preformat, ValidationError
from enum import Enum

def test_complete_workflow():
    class Priority(Enum):
        LOW = "low"
        HIGH = "high"

    class Task(BaseModel):
        title: str
        priority: Priority

        @preformat(['priority'])
        def normalize_priority(self, value):
            if isinstance(value, str):
                return Priority[value.upper()]
            return value

        @validator(['title'])
        def check_title(self, value):
            if not value.strip():
                raise ValidationError("Title required")

        @preformat(['title'])
        def clean_title(self, value):
            return value.strip()

    task = Task(title="  Test  ", priority="low")
    assert task.title == "Test"
    assert task.priority == Priority.LOW

    json_data = task.dump(_format="json")
    print(json_data)

    # loaded = Task.loads(json_data, _format="json")
    # assert loaded.title == "Test"
    # assert loaded.priority == Priority.LOW