# Formax

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
from formax import BaseModel, Field

class Person(BaseModel):
    name: str
    age: int = Field(gt=0)
```

---

## Validation Example

```python
Person(name="Alice", age=30)  # ✅ Valid
Person(name="Bob", age=-1)    # ❌ Raises ValidationError
```

---

## Formatting Hooks

```python
from formax import BaseModel, preformat

class Address(BaseModel):
    city: str

    @preformat(["city"])
    def format_city(self, value):
        return value.title()

addr = Address(city="london")
print(addr.city)  # Output: London
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

