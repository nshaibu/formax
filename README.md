# Pydantic-Mini

[![Build Status](https://github.com/nshaibu/pydantic-mini/actions/workflows/python_package.yml/badge.svg)](https://github.com/nshaibu/pydantic-mini/actions)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Status](https://img.shields.io/pypi/status/pydantic_mini.svg)](https://pypi.python.org/pypi/pydantic_mini)
[![Latest](https://img.shields.io/pypi/v/pydantic_mini.svg)](https://pypi.python.org/pypi/pydantic_mini)
[![PyV](https://img.shields.io/pypi/pyversions/pydantic_mini.svg)](https://pypi.python.org/pypi/pydantic_mini)
[![codecov](https://codecov.io/gh/nshaibu/pydantic-mini/graph/badge.svg?token=HBP9OC9IJJ)](https://codecov.io/gh/nshaibu/pydantic-mini)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=flat-square)](http://makeapullrequest.com)


## Table of Contents
- [Overview](#overview)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Core Concepts](#core-concepts)
- [API Reference](#api-reference)
- [Validation](#validation)
   - [Nested Validation](#nested-validation)
   - [Self-References and Forward References](#self-References-and-forward-references)
- [Preformatters](#preformatters)
- [Serialization](#serialization)
  - [Model Formatters](#model-formatters)
    - [Custom Formatters](#custom-formatters)
- [Configuration](#configuration)
- [Advanced Usage](#advanced-usage)
- [Examples](#examples)
- [Contributing](#contributing)
- [License](#license)

## Overview

Pydantic-mini is a lightweight Python library that extends the functionality of Python's native dataclass by providing built-in validation, serialisation, and support for custom validators. It is designed to be simple, minimalistic, and based entirely on Python's standard library, making it perfect for projects requiring data validation and object-relational mapping (ORM) without relying on third-party dependencies.

### Key Features

- **Type and Value Validation**: Enforces type validation for fields using field annotations with built-in validators for common field types
- **Custom Validators**: Easily define custom validation functions for specific fields
- **Serialisation Support**: Instances can be serialised to JSON, dictionaries, and CSV formats
- **Lightweight and Fast**: Built entirely on Python's standard library with no external dependencies
- **Multiple Input Formats**: Accepts data in various formats, including JSON, dictionaries, CSV, etc.
- **Simple ORM Capabilities**: Build lightweight ORMs for basic data management

## Installation

### From PyPI
```bash
pip install pydantic-mini
```

### From Source
```bash
git clone https://github.com/nshaibu/pydantic-mini.git
cd pydantic-mini
# Use the code directly in your project
```

## Quick Start

Here's a simple example to get you started:

```python
from pydantic_mini import BaseModel

class Person(BaseModel):
    name: str
    age: int

# Create an instance
person = Person(name="Alice", age=30)
print(person)  # Person(name='Alice', age=30)

# Validation happens automatically
try:
    invalid_person = Person(name="Bob", age="not_a_number")
except TypeError as e:
    print(f"Validation failed: {e}")
```

## Core Concepts

### BaseModel

`BaseModel` is the foundation class that all your data models should inherit from. It provides:
- Automatic type validation
- Serialization capabilities
- Custom validation support
- Configuration options

### MiniAnnotated

`MiniAnnotated` is used to add metadata and validation rules to fields:

```python
from pydantic_mini import BaseModel, MiniAnnotated, Attrib

class User(BaseModel):
    username: MiniAnnotated[str, Attrib(max_length=20)]
    age: MiniAnnotated[int, Attrib(gt=0, default=18)]
```

### Attrib

`Attrib` defines field attributes and validation rules:
- `default`: Default value for the field
- `default_factory`: Function to generate default value
- `pattern`: Regex pattern for string validation
- `validators`: List of custom validator functions
- `pre_formatter`: Function to format/preprocess the value before validation.
- `required`: Whether this field is required (default: False).
- `allow_none`: Whether None is allowed as a value (default: False).
- `gt`, `ge`, `lt`, `le`: Numeric comparison constraints.
- `min_length`, `max_length` (int, optional): Length constraints for sequences.

## API Reference

### BaseModel

The base class for all data models.

#### Class Methods

##### `loads(data, _format="dict")`
Load data from various formats into model instances.

**Parameters:**
- `data`: Input data (string, dict, or other format-specific data)
- `_format`: Format of input data (`"json"`, `"dict"`, `"csv"`)

**Returns:** Model instance or list of instances (for CSV)

**Example:**
```python
# From JSON string
json_data = '{"name": "John", "age": 30}'
person = Person.loads(json_data, _format="json")

# From dictionary
dict_data = {"name": "Alice", "age": 25}
person = Person.loads(dict_data, _format="dict")

# From CSV
csv_data = "name,age\nJohn,30\nAlice,25"
people = Person.loads(csv_data, _format="csv")
```

#### Instance Methods

##### `dump(_format="dict")`
Serialize the model instance to various formats.

**Parameters:**
- `_format`: Output format (`"json"`, `"dict"`, `"csv"`)

**Returns:** Serialized data in the specified format

**Example:**
```python
person = Person(name="John", age=30)

# To JSON string
json_output = person.dump(_format="json")

# To dictionary
dict_output = person.dump(_format="dict")
```

##### `__post_init__(self, **kwargs)`
Optional method for custom initialization logic.

**Example:**
```python
from typing import Optional
from dataclasses import InitVar

class DatabaseModel(BaseModel):
    id: int
    name: str
    database: InitVar[Optional[object]] = None
    
    def __post_init__(self, database):
        if database is not None:
            # Custom initialization logic
            self.id = database.get_next_id()
```

## Validation

### Type Validation

Pydantic-mini automatically validates field types based on annotations:

```python
class Product(BaseModel):
    name: str
    price: float
    quantity: int
    is_available: bool
```

### Built-in Validators

Use `Attrib` to add built-in validation rules:

```python
class User(BaseModel):
    username: MiniAnnotated[str, Attrib(max_length=20)]
    age: MiniAnnotated[int, Attrib(gt=18)]
    email: MiniAnnotated[str, Attrib(pattern=r"^\S+@\S+\.\S+$")]
    score: MiniAnnotated[float, Attrib(default=0.0)]
```

### Custom Field Validators

Define custom validation functions:

```python
from pydantic_mini.exceptions import ValidationError

def validate_not_kofi(instance: BaseModel, value: str):
    if value.lower() == "kofi":
        raise ValidationError("Kofi is not a valid name")

class Employee(BaseModel):
    name: MiniAnnotated[str, Attrib(validators=[validate_not_kofi])]
    department: str
```

### Method-based Validators

Define validators as methods with the pattern `validate_<field_name>`:

```python
class School(BaseModel):
    name: str
    students_count: int
    
    def validate_name(self, value, field):
        if len(value) > 50:
            raise ValidationError("School name too long")
        return value
    
    def validate_students_count(self, value, field):
        if value < 0:
            raise ValidationError("Students count cannot be negative")
        return value
```

### Global Validators

Apply validation rules to all fields:

```python
class StrictModel(BaseModel):
    field1: str
    field2: str
    field3: str
    
    def validate(self, value, field):
        if isinstance(value, str) and len(value) > 100:
            raise ValidationError(f"Field {field.name} is too long")
        return value
```

### Validator Notes

- **Transformation**: Validators can transform values by returning the modified value
- **Error Handling**: Validators must raise `ValidationError` when validation fails
- **Type Enforcement**: Type annotation constraints are enforced at runtime
- **Pre-formatting**: Use validators for formatting values before type checking

## Nested Validation

Pydantic-mini supports nested validation, allowing you to compose complex data models from simpler ones. When a field is annotated with another `BaseModel` class, the validation system automatically applies to the nested class and all its fields recursively. This enables you to build hierarchical data structures with comprehensive validation at every level.

### Basic Nested Validation

When you define a field using another `BaseModel` class, both the parent and nested models are fully validated:

```python
from pydantic_mini import BaseModel

class School(BaseModel):
    name: str
    location: str

class Person(BaseModel):
    name: str
    school: School
```

### Instantiation Methods

You can instantiate nested models in two ways:

#### 1. Using Nested Model Instances

```python
# Create nested model first
school = School(name="KNUST", location="Kumasi")
person = Person(name="Nafiu", school=school)

print(person.name)  # Output: Nafiu
print(person.school.name)  # Output: KNUST
print(person.school.location)  # Output: Kumasi
```

#### 2. Using Dictionary Auto-Conversion

```python
# Pass dictionary - automatically converted to School instance
person = Person(
    name="Nafiu",
    school={"name": "KNUST", "location": "Kumasi"}
)

print(person.school.name)  # Output: KNUST
print(type(person.school))  # Output: <class 'School'>
```

When a dictionary is provided for a nested `BaseModel` field, pydantic-mini automatically:
1. Detects that the field type is a `BaseModel` subclass
2. Converts the dictionary to an instance of that class
3. Applies all validation rules defined in the nested class

### Validation Propagation

All validation rules defined in nested models are fully enforced:

```python
from pydantic_mini import BaseModel, MiniAnnotated, Attrib
from pydantic_mini.exceptions import ValidationError

class School(BaseModel):
    name: MiniAnnotated[str, Attrib(max_length=50)]
    location: str
    student_count: MiniAnnotated[int, Attrib(gt=0)]
    
    def validate_name(self, value, field):
        if len(value) < 3:
            raise ValidationError("School name must be at least 3 characters")
        return value

class Person(BaseModel):
    name: MiniAnnotated[str, Attrib(max_length=30)]
    age: MiniAnnotated[int, Attrib(gt=0)]
    school: School

# Valid nested validation
person = Person(
    name="Nafiu",
    age=25,
    school={"name": "KNUST", "location": "Kumasi", "student_count": 5000}
)

# Invalid nested validation - will raise ValidationError
try:
    invalid_person = Person(
        name="John",
        age=20,
        school={"name": "AB", "location": "City", "student_count": -10}
    )
except ValidationError as e:
    print(f"Validation failed: {e}")
    # Errors: School name too short, student_count not greater than 0
```

### Multi-Level Nesting

You can nest models at multiple levels, and validation will propagate through all levels:

```python
class Address(BaseModel):
    street: str
    city: str
    postal_code: MiniAnnotated[str, Attrib(pattern=r"^\d{5}$")]

class School(BaseModel):
    name: str
    address: Address
    principal: str

class Person(BaseModel):
    name: str
    school: School

# Multi-level nested instantiation
person = Person(
    name="Nafiu",
    school={
        "name": "KNUST",
        "principal": "Dr. Smith",
        "address": {
            "street": "University Avenue",
            "city": "Kumasi",
            "postal_code": "12345"
        }
    }
)

print(person.school.address.city)  # Output: Kumasi
```

### Lists of Nested Models

You can also have collections of nested models:

```python
from typing import List

class Course(BaseModel):
    code: str
    title: str
    credits: MiniAnnotated[int, Attrib(gt=0)]

class Student(BaseModel):
    name: str
    courses: List[Course]

# Instantiate with list of dictionaries
student = Student(
    name="Alice",
    courses=[
        {"code": "CS101", "title": "Intro to Programming", "credits": 3},
        {"code": "CS201", "title": "Data Structures", "credits": 4},
        {"code": "MATH101", "title": "Calculus I", "credits": 3}
    ]
)

# All courses are validated Course instances
for course in student.courses:
    print(f"{course.code}: {course.title} ({course.credits} credits)")
```

### Non-BaseModel Nested Classes

**Important**: Nested validation only works for `BaseModel` subclasses. If you use a regular Python class or standard dataclass, only the class instance itself is validated, **not** the fields within it.

#### Example with Regular Python Class

```python
# Regular Python class (not BaseModel)
class School:
    def __init__(self, name: str, location: str):
        self.name = name
        self.location = location

class Person(BaseModel):
    name: str
    school: School

# You must pass a School instance - dictionaries won't work
school = School(name="KNUST", location="Kumasi")
person = Person(name="Nafiu", school=school)

# This will FAIL - dictionaries not auto-converted for non-BaseModel classes
try:
    person = Person(
        name="Nafiu",
        school={"name": "KNUST", "location": "Kumasi"}
    )
except TypeError as e:
    print(f"Error: {e}")  # Expected School instance, got dict

# Field validation is NOT applied to School's internal fields
# Only type checking that 'school' is a School instance occurs
school_invalid = School(name="", location="")  # No validation errors!
person = Person(name="Nafiu", school=school_invalid)  # This works!
```

#### Example with Standard Dataclass

```python
from dataclasses import dataclass

# Standard dataclass (not BaseModel)
@dataclass
class School:
    name: str
    location: str

class Person(BaseModel):
    name: str
    school: School

# Must pass School instance
school = School(name="KNUST", location="Kumasi")
person = Person(name="Nafiu", school=school)

# No field validation for School's attributes
# No automatic dictionary conversion
```

## Self References and Forward References

`pydantic-mini` fully supports self-referential models and forward references. 
Unlike basic dataclasses, it automatically resolves string-based type hints and recursively
inflates nested data into model instances during initialization.

### Recursive Tree Structures

You can define tree-like structures by referencing the class name as a string. These are automatically resolved and validated.

```python
from typing import Optional, List
from pydantic_mini import BaseModel, MiniAnnotated, Attrib

class TreeNode(BaseModel):
    value: int
    # Self-reference resolved at runtime
    children: MiniAnnotated[List['TreeNode'], Attrib(default_factory=list)]

# Automatic conversion to TreeNode instances
# Nested dictionaries are recursively inflated
root = TreeNode.loads({
    "value": 1, 
    "children": [
        {"value": 2, "children": []}, 
        {"value": 3, "children": [{"value": 4}]}
    ]
}, _format="dict")

assert isinstance(root.children[0], TreeNode)
assert root.children[1].children[0].value == 4
```

### Forward References

Models can reference other models defined later in the same module or in different modules.

```python
class Parent(BaseModel):
    name: str
    # 'Child' is defined below but will be resolved successfully
    first_born: MiniAnnotated["Child", Attrib()]

class Child(BaseModel):
    age: int

# Full validation and inflation even with forward references
p = Parent.loads({"name": "John", "first_born": {"age": 10}}, _format="dict")
assert isinstance(p.first_born, Child)
```

### Optional Nested Models

Nested models can be optional:

```python
from typing import Optional

class ContactInfo(BaseModel):
    email: MiniAnnotated[str, Attrib(pattern=r"^\S+@\S+\.\S+$")]
    phone: str

class Person(BaseModel):
    name: str
    contact: Optional[ContactInfo] # No need to assign = None

# Without contact info
person1 = Person(name="Alice")
print(person1.contact)  # Output: None

# With contact info
person2 = Person(
    name="Bob",
    contact={"email": "bob@example.com", "phone": "+1234567890"}
)
print(person2.contact.email)  # Output: bob@example.com
```

**Note on Optional Fields**: When you annotate a field with typing.Optional, you don't need to explicitly assign None as the default value (i.e., field: `Optional[Type] = None`). The library automatically handles Optional annotations and treats the field as having a None default value. Simply writing field: `Optional[Type]` is sufficient.
```python
from typing import Optional

class User(BaseModel):
    name: str
    # These are equivalent:
    email: Optional[str]           # Automatic None default
    phone: Optional[str] = None    # Explicit None default (redundant but valid)
    
    # Both fields will default to None if not provided
    address: Optional[str]         # Library handles this automatically

# All optional fields default to None
user = User(name="Alice")
print(user.email)    # Output: None
print(user.phone)    # Output: None
print(user.address)  # Output: None
```

### Serialization of Nested Models

Nested models are properly serialized to all supported formats:

```python
class Address(BaseModel):
    city: str
    country: str

class Person(BaseModel):
    name: str
    address: Address

person = Person(
    name="Nafiu",
    address={"city": "Kumasi", "country": "Ghana"}
)

# Serialize to dictionary
person_dict = person.dump(_format="dict")
print(person_dict)
# Output: {'name': 'Nafiu', 'address': {'city': 'Kumasi', 'country': 'Ghana'}}

# Serialize to JSON
person_json = person.dump(_format="json")
print(person_json)
# Output: '{"name": "Nafiu", "address": {"city": "Kumasi", "country": "Ghana"}}'

# Load from JSON with nested validation
loaded_person = Person.loads(person_json, _format="json")
print(type(loaded_person.address))  # Output: <class 'Address'>
```

### Complex Nested Example

Here's a comprehensive example demonstrating nested validation with multiple levels:

```python
from typing import List, Optional
from enum import Enum

class Grade(Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    F = "F"

class Course(BaseModel):
    code: MiniAnnotated[str, Attrib(pattern=r"^[A-Z]{2,4}\d{3}$")]
    title: MiniAnnotated[str, Attrib(max_length=100)]
    credits: MiniAnnotated[int, Attrib(gt=0, default=3)]
    grade: Optional[Grade] = None
    
    def validate_credits(self, value, field):
        if value > 6:
            raise ValidationError("Course credits cannot exceed 6")
        return value

class Semester(BaseModel):
    year: MiniAnnotated[int, Attrib(gt=2000)]
    term: MiniAnnotated[str, Attrib(pattern=r"^(Fall|Spring|Summer)$")]
    courses: List[Course]
    gpa: MiniAnnotated[float, Attrib(gt=0.0, default=0.0)]
    
    def validate_courses(self, value, field):
        if len(value) > 7:
            raise ValidationError("Cannot enroll in more than 7 courses per semester")
        return value

class Student(BaseModel):
    student_id: MiniAnnotated[str, Attrib(pattern=r"^\d{8}$")]
    name: str
    major: str
    semesters: List[Semester]
    
    def validate_student_id(self, value, field):
        if not value.startswith("20"):
            raise ValidationError("Student ID must start with '20'")
        return value

# Create a student with nested validation at multiple levels
student = Student(
    student_id="20123456",
    name="Nafiu Shaibu",
    major="Computer Science",
    semesters=[
        {
            "year": 2023,
            "term": "Fall",
            "gpa": 3.8,
            "courses": [
                {"code": "CS101", "title": "Intro to Programming", "credits": 3, "grade": "A"},
                {"code": "MATH201", "title": "Calculus II", "credits": 4, "grade": "B"},
                {"code": "ENG101", "title": "English Composition", "credits": 3, "grade": "A"}
            ]
        },
        {
            "year": 2024,
            "term": "Spring",
            "gpa": 3.9,
            "courses": [
                {"code": "CS201", "title": "Data Structures", "credits": 4},
                {"code": "CS221", "title": "Computer Architecture", "credits": 3}
            ]
        }
    ]
)

# Access deeply nested validated data
print(f"Student: {student.name}")
print(f"First semester GPA: {student.semesters[0].gpa}")
print(f"First course: {student.semesters[0].courses[0].title}")

# Serialize with all nested data
student_json = student.dump(_format="json")
# All nested models properly serialized
```

### Best Practices for Nested Validation

1. **Use BaseModel for Nested Classes**: Always inherit from `BaseModel` for nested models to get full validation support
2. **Dictionary Convenience**: Leverage automatic dictionary-to-model conversion for cleaner instantiation code
3. **Validate Early**: Define validation rules at the appropriate level - validate school data in the School model, not in Person
4. **Avoid Deep Nesting**: While supported, excessive nesting (>3-4 levels) can make models hard to maintain
5. **Document Relationships**: Clearly document parent-child relationships in docstrings
6. **Type Hints**: Always use proper type hints for nested fields to enable automatic conversion
7. **Optional Nesting**: Use `Optional[]` for nested models that may not always be present


## Preformatters

Preformatters are callables that transform field values **before** validation occurs. While validators can also transform values, they do so **after** validation has been performed. Preformatters allow you to modify or convert input data into the expected format before any type checking or validation rules are applied.

### When to Use Preformatters

Preformatters are particularly useful for:
- Converting string representations to enum values
- Transforming dictionaries into custom objects
- Normalizing data formats before validation
- Type coercion that needs to happen before type checking
- Conditional transformations based on input type

### Defining a Preformatter

A preformatter is a function that takes a single value argument and returns the transformed value:

```python
def to_pow2(x: int) -> int:
    """Square the input value."""
    return x ** 2
```

Assign the preformatter to the `pre_formatter` argument in `Attrib`:

```python
class MathModel(BaseModel):
    squared_value: MiniAnnotated[int, Attrib(pre_formatter=to_pow2)]

# Usage
model = MathModel(squared_value=5)
print(model.squared_value)  # Output: 25
```

### Execution Order

Understanding the order of operations is crucial:

1. **Preformatter** - Transforms the raw input value
2. **Type Validation** - Checks if the value matches the field's type annotation
3. **Built-in Validators** - Applies Attrib validators (max_length, gt, pattern, etc.)
4. **Custom Validators** - Applies custom validation functions
5. **Method Validators** - Applies validate_<field_name> methods

### Basic Example

```python
from pydantic_mini import BaseModel, MiniAnnotated, Attrib

def uppercase_formatter(value: str) -> str:
    """Convert string to uppercase before validation."""
    if isinstance(value, str):
        return value.upper()
    return value

class User(BaseModel):
    username: MiniAnnotated[str, Attrib(
        pre_formatter=uppercase_formatter,
        max_length=20
    )]

# The username will be converted to uppercase before validation
user = User(username="john_doe")
print(user.username)  # Output: JOHN_DOE
```

### Enum Resolution Example

A common use case is converting string values to enum instances:

```python
from enum import Enum
from typing import Union
from pydantic_mini.exceptions import ValidationError

class Status(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"

def resolve_str_to_enum(
    enum_klass: type[Enum], 
    value: str, 
    use_lower_case: bool = False
) -> Union[Enum, str]:
    """Resolve string value to enum instance."""
    if not isinstance(value, str):
        return value
    
    attr_name = value.lower() if use_lower_case else value.upper()
    enum_attr = getattr(enum_klass, attr_name, None)
    
    if enum_attr is None:
        raise ValidationError(
            f"Invalid enum value {value} for {enum_klass.__name__}",
            code="invalid_enum"
        )
    
    return enum_attr

class Task(BaseModel):
    name: str
    status: MiniAnnotated[
        Status,
        Attrib(
            default=Status.PENDING,
            pre_formatter=lambda val: resolve_str_to_enum(
                Status, val, use_lower_case=False
            )
        )
    ]

# Usage - string automatically converted to enum
task = Task(name="Deploy", status="ACTIVE")
print(task.status)  # Output: Status.ACTIVE
print(type(task.status))  # Output: <enum 'Status'>
```

### Dictionary to Model Conversion

Preformatters can convert nested dictionaries into model instances:

```python
class Address(BaseModel):
    street: str
    city: str
    country: str

class Person(BaseModel):
    name: str
    address: MiniAnnotated[
        Address,
        Attrib(
            pre_formatter=lambda val: (
                Address.loads(val, _format="dict")
                if isinstance(val, dict)
                else val
            )
        )
    ]

# Automatically converts dictionary to Address instance
person = Person(
    name="Alice",
    address={"street": "123 Main St", "city": "New York", "country": "USA"}
)

print(person.address.city)  # Output: New York
```

### Complex Example from Volnux

Here's a real-world example from the [Volnux](https://github.com/nshaibu/volnux) project demonstrating advanced preformatter usage:

```python
import typing
from enum import Enum
from dataclasses import dataclasses

class ResultEvaluationStrategy(Enum):
    ALL_MUST_SUCCEED = "all_must_succeed"
    ANY_MUST_SUCCEED = "any_must_succeed"

class StopCondition(Enum):
    ON_FIRST_SUCCESS = "on_first_success"
    ON_FIRST_FAILURE = "on_first_failure"

class ExecutorInitializerConfig(BaseModel):
    max_workers: int = 4
    thread_name_prefix: str = "Executor"

def resolve_str_to_enum(
    enum_klass: typing.Type[Enum], 
    value: str, 
    use_lower_case: bool = False
) -> typing.Union[Enum, str]:
    """Resolve enum value to enum class."""
    if not isinstance(value, str):
        return value
    
    attr_name = value.lower() if use_lower_case else value.upper()
    enum_attr = getattr(enum_klass, attr_name, None)
    
    if enum_attr is None:
        raise ValidationError(
            f"Invalid enum value {value} for {enum_klass.__name__}", 
            code="invalid_enum"
        )
    
    return enum_attr

class Options(BaseModel):
    """
    Task execution configuration options that can be passed to a task or
    task groups in pointy scripts, e.g., A[retry_attempts=3], {A->B}[retry_attempts=3].
    """
    
    # Core execution options with validation
    retry_attempts: MiniAnnotated[int, Attrib(default=0, ge=0)]
    executor: MiniAnnotated[typing.Optional[str], Attrib(default=None)]
    
    # Configuration dictionaries with preformatter
    executor_config: MiniAnnotated[
        typing.Union[ExecutorInitializerConfig, dict],
        Attrib(
            default_factory=lambda: ExecutorInitializerConfig(),
            pre_formatter=lambda val: (
                ExecutorInitializerConfig.from_dict(val)
                if isinstance(val, dict)
                else val
            ),
        ),
    ]
    extras: MiniAnnotated[dict, Attrib(default_factory=dict)]
    
    # Execution state and control with enum preformatters
    result_evaluation_strategy: MiniAnnotated[
        ResultEvaluationStrategy,
        Attrib(
            default=ResultEvaluationStrategy.ALL_MUST_SUCCEED,
            pre_formatter=lambda val: resolve_str_to_enum(
                ResultEvaluationStrategy, val, use_lower_case=False
            ),
        ),
    ]
    stop_condition: MiniAnnotated[
        typing.Union[StopCondition, None],
        Attrib(
            default=None,
            pre_formatter=lambda val: val
            and resolve_str_to_enum(StopCondition, val, use_lower_case=False)
            or None,
        ),
    ]
    bypass_event_checks: typing.Optional[bool]
    
    class Config:
        disable_typecheck = False
        disable_all_validation = False
    
    @classmethod
    def from_dict(cls, options_dict: typing.Dict[str, typing.Any]) -> "Options":
        """
        Create Options instance from dictionary, placing unknown fields in extras.
        
        Args:
            options_dict: Dictionary containing option values
            
        Returns:
            Options instance with known fields populated and unknown fields in extras
        """
        known_fields = {field.name for field in dataclasses.fields(cls)}
        
        option = {}
        for field_name, value in options_dict.items():
            if field_name in known_fields:
                option[field_name] = value
            else:
                # Place unknown fields in extras
                if "extras" not in option:
                    option["extras"] = {}
                option["extras"][field_name] = value
        
        return cls.loads(option, _format="dict")

# Usage example
options = Options(
    retry_attempts=3,
    executor_config={"max_workers": 8, "thread_name_prefix": "Worker"},
    result_evaluation_strategy="ALL_MUST_SUCCEED",  # String converted to enum
    stop_condition="ON_FIRST_FAILURE"  # String converted to enum
)

print(options.executor_config.max_workers)  # Output: 8
print(options.result_evaluation_strategy)  # Output: ResultEvaluationStrategy.ALL_MUST_SUCCEED
```

### Best Practices

1. **Type Checking**: Always check the input type before transformation to handle various input formats gracefully
2. **Error Handling**: Raise `ValidationError` for invalid transformations that cannot be resolved
3. **Idempotency**: Ensure preformatters can handle already-transformed values (e.g., enum already being an enum)
4. **Lambda Functions**: Use lambda functions for simple, inline transformations
5. **Dedicated Functions**: Create dedicated functions for complex or reusable transformation logic

### Preformatter vs Validator

| Aspect | Preformatter | Validator |
|--------|-------------|-----------|
| Execution timing | Before validation | After validation |
| Primary purpose | Data transformation | Data validation |
| Type checking | Happens after | Already completed |
| Use case | Format conversion | Business rule enforcement |
| Return value | Transformed value | Validated/transformed value |

### Combined Example

Preformatters and validators work together seamlessly:

```python
def strip_whitespace(value: str) -> str:
    """Preformatter: Remove leading/trailing whitespace."""
    if isinstance(value, str):
        return value.strip()
    return value

def validate_no_numbers(instance, value: str) -> str:
    """Validator: Ensure no digits in string."""
    if any(char.isdigit() for char in value):
        raise ValidationError("Value cannot contain numbers")
    return value

class CleanModel(BaseModel):
    clean_text: MiniAnnotated[
        str,
        Attrib(
            pre_formatter=strip_whitespace,
            validators=[validate_no_numbers],
            max_length=50
        )
    ]

# Execution order:
# 1. Preformatter strips whitespace: "  hello  " → "hello"
# 2. Type validation: Check if string
# 3. Built-in validator: Check max_length
# 4. Custom validator: Check for numbers

model = CleanModel(clean_text="  hello world  ")
print(model.clean_text)  # Output: "hello world"
```

## Serialization

### Supported Formats

Pydantic-mini supports three serialization formats:

#### JSON
```python
person = Person(name="John", age=30)

# Serialize to JSON
json_str = person.dump(_format="json")
print(json_str)  # '{"name": "John", "age": 30}'

# Deserialize from JSON
person = Person.loads('{"name": "Alice", "age": 25}', _format="json")
```

#### Dictionary
```python
# Serialize to dictionary
person_dict = person.dump(_format="dict")
print(person_dict)  # {'name': 'John', 'age': 30}

# Deserialize from dictionary
person = Person.loads({"name": "Bob", "age": 35}, _format="dict")
```

#### CSV
```python
# Deserialize from CSV (returns list of instances)
csv_data = "name,age\nJohn,30\nAlice,25\nBob,35"
people = Person.loads(csv_data, _format="csv")

for person in people:
    print(person)
```

## Model Formatters

Model formatters in pydantic-mini define how a model is loaded from and dumped to
external representations such as `JSON`, `dicts`, `CSV`, or custom formats like `YAML` or `TOML`.

They operate at the model boundary and are responsible for full-model serialization and deserialization.

Model formatters are used by:

```
BaseModel.loads(data, _format=...) → decode / read

BaseModel.dump(_format=...) → encode / write
```

### Custom Formatters

To create a custom formatter, you need to inherit from `BaseModelFormatter` and implement the `encode` (reading data) and `decode` (writing data) methods.

#### Formatter Base Classes

##### BaseModelFormatter
- Low-level base class for custom formats
- Use only for non-dict-like formats or full control

##### DictModelFormatter (recommended)
- Handles recursive model inflation and nested BaseModel instances
- Supports lists and primitive type handling
- You only need to convert external format ↔ dict/list

#### Required Interface
`format_name`
```python
format_name = "yaml"
# or with aliases
format_name = ("yaml", "yml")
```
- Matched against the _format parameter

`encode(self, _type, obj)`
- Used when loading data into a model
- `_type`: target BaseModel class
- `obj`: raw external input (usually string)
- Returns dict/list suitable for model inflation

`decode(self, instance)`
- Used when dumping a model
- `instance`: BaseModel instance or nested data
- Returns serialized output (usually string)

#### Example
#### 1. Creating a YAML Formatter

Here is an example of how to add YAML support using the `PyYAML` library.

```python
import yaml
from typing import Type, Any
from pydantic_mini.formatters import BaseModelFormatter, DictModelFormatter

class YAMLModelFormatter(DictModelFormatter):
    """
    A custom formatter for YAML support.
    Inheriting from DictModelFormatter allows us to reuse 
    the dictionary-to-model logic.
    """
    format_name = "yaml"

    def encode(self, _type: Type["BaseModel"], obj: str) -> Any:
        # Convert YAML string to dict
        data = yaml.safe_load(obj)
        # Leverage DictModelFormatter logic to inflate models
        return super().encode(_type, data)

    def decode(self, instance: Any) -> str:
        # Leverage DictModelFormatter to get a raw dict/list
        data = super().decode(instance)
        # Convert dict to YAML string
        return yaml.dump(data)
```

#### 2. Using the Custom Formatter

Once the class is defined, it is automatically registered. You can use it via the standard `.loads()` and `.dump()` methods on any `BaseModel`.

```python
class Task(BaseModel):
    name: str
    priority: int

yaml_data = """
name: "System Update"
priority: 1
"""

# The library finds 'YAMLModelFormatter' via the 'yaml' key
task = Task.loads(yaml_data, _format="yaml")
print(task.name) # Output: System Update

# Exporting back to YAML
print(task.dump(_format="yaml"))
```

#### 3. Implementation Guidelines

1. **Discovery**: As long as your formatter is imported in your runtime, it will be available.

2. **DictModelFormatter as a Base**: It is highly recommended to inherit from `DictModelFormatter` rather than the raw BaseModelFormatter. This allows you to focus only on the string-to-dict conversion while the base class handles the complex recursive model inflation.

3. **The format_name**: This string is the key used in the `_format` parameter. You can also provide a list or tuple of names if you want to support aliases (e.g., format_name = ("yaml", "yml")).

## Configuration

### Model Configuration

Configure model behavior using the `Config` class:

```python
import os
from datetime import datetime
import typing

class EventResult(BaseModel):
    error: bool
    task_id: str
    event_name: str
    content: typing.Any
    init_params: typing.Optional[typing.Dict[str, typing.Any]]
    call_params: typing.Optional[typing.Dict[str, typing.Any]]
    process_id: MiniAnnotated[int, Attrib(default_factory=lambda: os.getpid())]
    creation_time: MiniAnnotated[float, Attrib(default_factory=lambda: datetime.now().timestamp())]
    
    class Config:
        unsafe_hash = False
        frozen = False
        eq = True
        order = False
        disable_typecheck = False
        disable_all_validation = False
```

### Configuration Options

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `init` | `bool` | `True` | Whether the `__init__` method is generated for the dataclass |
| `repr` | `bool` | `True` | Whether a `__repr__` method is generated |
| `eq` | `bool` | `True` | Enables the generation of `__eq__` for comparisons |
| `order` | `bool` | `False` | Enables ordering methods (`__lt__`, `__gt__`, etc.) |
| `unsafe_hash` | `bool` | `False` | Allows an unsafe implementation of `__hash__` |
| `frozen` | `bool` | `False` | Makes the dataclass instances immutable |
| `strict_mode` | `bool` | `False` | Disable or enable automatic type coercion |
| `disable_typecheck` | `bool` | `False` | Disable runtime type checking in models |
| `disable_all_validation` | `bool` | `False` | Disable all validation logic (type + custom rules) |

## Advanced Usage

### Using InitVar

For fields that are only used during initialization:

```python
from dataclasses import InitVar
import typing

class DatabaseRecord(BaseModel):
    id: int
    name: str
    database: InitVar[typing.Optional[object]] = None
    
    def __model_init__(self, database):
        if database is not None and self.id is None:
            self.id = database.get_next_id()
```

### Default Factories

Use `default_factory` for dynamic default values:

```python
import uuid
from datetime import datetime

class Task(BaseModel):
    id: MiniAnnotated[str, Attrib(default_factory=lambda: str(uuid.uuid4()))]
    created_at: MiniAnnotated[float, Attrib(default_factory=lambda: datetime.now().timestamp())]
    title: str
    completed: MiniAnnotated[bool, Attrib(default=False)]
```

### Simple ORM Usage

Create lightweight ORMs for in-memory data management:

```python
class PersonORM:
    def __init__(self):
        self.people_db = []
    
    def create(self, **kwargs):
        person = Person(**kwargs)
        self.people_db.append(person)
        return person
    
    def find_by_age(self, min_age):
        return [p for p in self.people_db if p.age >= min_age]
    
    def find_by_name(self, name):
        return [p for p in self.people_db if p.name == name]

# Usage
orm = PersonORM()
orm.create(name="John", age=30)
orm.create(name="Alice", age=25)
orm.create(name="Bob", age=35)

adults = orm.find_by_age(18)
johns = orm.find_by_name("John")
```

## Examples

### Complete User Management Example

```python
import re
from typing import Optional, List
from pydantic_mini import BaseModel, MiniAnnotated, Attrib
from pydantic_mini.exceptions import ValidationError

def validate_strong_password(instance, password: str):
    """Validate password strength."""
    if len(password) < 8:
        raise ValidationError("Password must be at least 8 characters long")
    if not re.search(r"[A-Z]", password):
        raise ValidationError("Password must contain at least one uppercase letter")
    if not re.search(r"[a-z]", password):
        raise ValidationError("Password must contain at least one lowercase letter")
    if not re.search(r"\d", password):
        raise ValidationError("Password must contain at least one digit")
    return password

def validate_username(instance, username: str):
    """Validate username format."""
    if not re.match(r"^[a-zA-Z0-9_]+$", username):
        raise ValidationError("Username can only contain letters, numbers, and underscores")
    return username.lower()

class User(BaseModel):
    username: MiniAnnotated[str, Attrib(
        max_length=30, 
        validators=[validate_username]
    )]
    email: MiniAnnotated[str, Attrib(
        pattern=r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    )]
    password: MiniAnnotated[str, Attrib(validators=[validate_strong_password])]
    age: MiniAnnotated[int, Attrib(gt=13, default=18)]
    is_active: MiniAnnotated[bool, Attrib(default=True)]
    roles: Optional[List[str]] = None
    
    def validate_age(self, value, field):
        if value > 120:
            raise ValidationError("Age seems unrealistic")
        return value
    
    class Config:
        frozen = False
        eq = True

# Usage example
try:
    user = User(
        username="JohnDoe123",
        email="john@example.com",
        password="SecurePass123",
        age=25,
        roles=["user", "admin"]
    )
    
    # Serialize user
    user_json = user.dump(_format="json")
    print("User JSON:", user_json)
    
    # Load from JSON
    loaded_user = User.loads(user_json, _format="json")
    print("Loaded user:", loaded_user)
    
except ValidationError as e:
    print(f"Validation error: {e}")
```

### E-commerce Product Example

```python
from decimal import Decimal
from typing import Optional, List
from enum import Enum

class ProductStatus(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DISCONTINUED = "discontinued"

def validate_price(instance, price: float):
    if price < 0:
        raise ValidationError("Price cannot be negative")
    if price > 1000000:
        raise ValidationError("Price too high")
    return round(price, 2)

def validate_sku(instance, sku: str):
    if not re.match(r"^[A-Z]{2,3}-\d{4,6}$", sku):
        raise ValidationError("SKU must be in format XX-NNNN or XXX-NNNNNN")
    return sku.upper()

class Product(BaseModel):
    name: MiniAnnotated[str, Attrib(max_length=100)]
    sku: MiniAnnotated[str, Attrib(validators=[validate_sku])]
    price: MiniAnnotated[float, Attrib(validators=[validate_price])]
    description: Optional[str] = None
    category: str
    tags: Optional[List[str]] = None
    stock_quantity: MiniAnnotated[int, Attrib(default=0)]
    status: str = ProductStatus.ACTIVE.value
    
    def validate_stock_quantity(self, value, field):
        if value < 0:
            raise ValidationError("Stock quantity cannot be negative")
        return value
    
    def validate_category(self, value, field):
        valid_categories = ["electronics", "clothing", "books", "home", "sports"]
        if value.lower() not in valid_categories:
            raise ValidationError(f"Category must be one of: {valid_categories}")
        return value.lower()

# Create products
products = [
    Product(
        name="Wireless Headphones",
        sku="EL-1234",
        price=99.99,
        description="High-quality wireless headphones",
        category="electronics",
        tags=["wireless", "audio", "bluetooth"],
        stock_quantity=50
    ),
    Product(
        name="Python Programming Book",
        sku="BK-5678",
        price=29.99,
        category="books",
        stock_quantity=25
    )
]

# Serialize to JSON
products_json = [p.dump(_format="json") for p in products]
print("Products JSON:", products_json)
```

## Error Handling

### ValidationError

All validation failures raise `ValidationError`:

```python
from pydantic_mini.exceptions import ValidationError

try:
    user = User(username="", email="invalid-email", age=-5)
except ValidationError as e:
    print(f"Validation failed: {e}")
    # Handle the error appropriately
```

### Best Practices for Error Handling

```python
def create_user_safely(user_data):
    try:
        user = User.loads(user_data, _format="dict")
        return {"success": True, "user": user}
    except ValidationError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Unexpected error: {e}"}

# Usage
result = create_user_safely({
    "username": "testuser",
    "email": "test@example.com",
    "password": "SecurePass123"
})

if result["success"]:
    print("User created:", result["user"])
else:
    print("Error:", result["error"])
```

## Performance Considerations

### Disabling Validation

For performance-critical scenarios, you can disable validation:

```python
class FastModel(BaseModel):
    field1: str
    field2: int
    
    class Config:
        disable_typecheck = True
        disable_all_validation = True
```

### Efficient Serialization

Choose the appropriate serialization format based on your needs:
- Use `dict` format for Python-to-Python communication
- Use `json` format for API responses and storage
- Use `csv` format for data export and reporting

## Contributing

Contributions are welcome! To contribute to pydantic-mini:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass
6. Submit a pull request

### Development Setup

```bash
git clone https://github.com/nshaibu/pydantic-mini.git
cd pydantic-mini
# Set up your development environment
# Run tests
python -m pytest tests/
```

### Code Style

- Follow PEP 8 style guidelines
- Use type hints for all functions and methods
- Add docstrings for public APIs
- Write comprehensive tests for new features

## License

Pydantic-mini is open-source and available under the GPL License.

## Changelog

### Future Releases
- Additional built-in validators
- Performance optimisations
- Extended serialisation formats

---

*This documentation is for pydantic-mini, a lightweight alternative to Pydantic with zero external dependencies.*
