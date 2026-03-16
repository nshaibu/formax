# Formax

**Formax — Fast, Flexible, Fully Validated Python Models.**

High-performance Python model builder and validation engine with configurable performance tiers.  
Formax is designed for developers who want the flexibility of modern validation frameworks with the speed of lightweight data models.

---

[![Build Status](https://github.com/nshaibu/formax/actions/workflows/python_package.yml/badge.svg)](https://github.com/nshaibu/formax/actions)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Status](https://img.shields.io/pypi/status/formax-py.svg)](https://pypi.python.org/pypi/formax-py)
[![Latest](https://img.shields.io/pypi/v/formax-py.svg)](https://pypi.python.org/pypi/formax-py)
[![PyV](https://img.shields.io/pypi/pyversions/formax-py.svg)](https://pypi.python.org/pypi/formax-py)
[![codecov](https://codecov.io/gh/nshaibu/formax/graph/badge.svg?token=HBP9OC9IJJ)](https://codecov.io/gh/nshaibu/formax)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=flat-square)](http://makeapullrequest.com)
---

## Quick Example

```python
from formax import BaseModel

class User(BaseModel):
    id: int
    name: str
    active: bool

user = User(id=1, name="Alice", active=True)
print(user.name)  # Output: Alice
````

---

## Features

* ⚡ High-performance model construction
* 🧩 Configurable validation tiers
* 🏗 Class builder with schema enforcement
* 🔍 Type validation and constraint support
* 🔌 Extensible serialization formatters
* 🧠 Descriptor-based field specialization
* 📦 Zero runtime dependencies

---

## Performance

Formax is optimized for speed and minimal overhead.

| Library            | Mean init time |
| ------------------ | -------------- |
| Formax (fast mode) | **~585 ns**    |
| Dataclasses        | ~680 ns        |
| Pydantic           | ~1.5 µs        |

Benchmarks run on Python 3.10.

---

## Installation

```bash
pip install formax-py
```

---

## Model Features

```python
from formax import BaseModel, Attrib, MiniAnnotated

class Person(BaseModel):
    name: str
    age: MiniAnnotated[int, Attrib(gt=0, lt=120)]
    email: MiniAnnotated[str, Attrib(pattern=r"^\S+@\S+\.\S+$")]

Person(name="Alice", age=30, email="alice@example.com")  # ✅ Valid
Person(name="Bob", age=-1, email="bob@example")    # ❌ Raises ValidationError
```

---

## Validation Hooks

```python
from formax import BaseModel, validator

class User(BaseModel):
    password: str
    confirm_password: str
    
    @validator(["password", "confirm_password"], order=1)
    def validate_password_length(self, value):
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters long")
    
    @validator(["confirm_password"], order=10)
    def validate_passwords_match(self, value):
        if value != self.password:
            raise ValueError("Passwords do not match")
```

---


## Formatting Hooks

```python
from datetime import datetime
from formax import BaseModel, preformat, postformat

class Address(BaseModel):
    city: str
    timestamp: float
    
    @preformat(["city"], order=1)
    def format_city(self, value) -> str:
        return value.title()
    
    @preformat(["timestamp"], order=1)
    def format_timestamp(self, value: datetime) -> float:
        return value.timestamp()
    
    @postformat(["timestamp"], order=1)
    def postformat_timestamp(self, value: float) -> datetime:
        return datetime.fromtimestamp(value)
    
addr = Address(city="london", timestamp=datetime.now())
print(addr.city)  # Output: London
print(addr.timestamp)  # Output: datetime object
```

---

## Configurable Performance Tiers

Formax allows validation to be tuned at class definition time.

```python
from formax import BaseModel, ValidationFlags, InitStrategy

class User(BaseModel):
    id: int

    class Config:
        validation = ValidationFlags.TYPECHECK
        init_strategy = InitStrategy.FAST
```

Balance **speed** and **validation strictness**.

---

## Comparison

| Feature                  | Formax | Pydantic | Dataclasses |
| ------------------------ | ------ | -------- | ----------- |
| Validation               | ✓      | ✓        | ✗           |
| Configurable performance | ✓      | ✗        | ✗           |
| Zero dependencies        | ✓      | ✗        | ✓           |
| Extensible formatting    | ✓      | ✓        | ✗           |

---

## Philosophy

Formax focuses on:

* Predictable performance
* Explicit validation control
* Minimal runtime overhead

---

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

---

## License

GPLv3

