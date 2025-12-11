<!--
SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>

SPDX-License-Identifier: ISC
-->

# API Reference

Comprehensive API documentation for apywire.

## Core Classes

### Wiring

::: apywire.Wiring
    options:
      show_source: false
      members:
        - __init__

### WiringRuntime

::: apywire.WiringRuntime
    options:
      show_source: false

### WiringCompiler

::: apywire.WiringCompiler
    options:
      show_source: false
      members:
        - __init__
        - compile

### WiringBase

::: apywire.WiringBase
    options:
      show_source: false

### Generator

::: apywire.Generator
        options:
            show_source: false
            members:
                - generate

## Accessor Types

### Accessor

::: apywire.Accessor
    options:
      show_source: false

### AioAccessor

::: apywire.AioAccessor
    options:
      show_source: false

## Type Aliases

### Spec

```python
from apywire import Spec

Spec = dict[str, dict[str | int, Any] | list[Any] | ConstantValue]
```

The `Spec` type represents the wiring specification dictionary. It maps wiring keys to configuration:

- **Wiring keys** with format `"module.Class name"` define objects to be wired
- **Simple keys** without a class become constants
- **Values** can be dictionaries (keyword args), lists (positional args), or constants

Example:

```python
from apywire import Spec

spec: Spec = {
    "datetime.datetime now": {"year": 2025, "month": 1, "day": 1},
    "pathlib.Path root": ["/home/user"],
    "port": 8080,  # Constant
}
```

### SpecEntry

```python
from apywire import SpecEntry

SpecEntry = dict[str | int, Any]
```

The `SpecEntry` type represents a single entry in the spec (the configuration for one wired object):

```python
from apywire import SpecEntry

entry: SpecEntry = {
    "year": 2025,
    "month": 1,
    "day": 1,
}
```

## Exception Classes

### WiringError

::: apywire.WiringError
    options:
      show_source: false

Base exception class for all apywire errors.

### CircularWiringError

::: apywire.CircularWiringError
    options:
      show_source: false

Raised when a circular dependency is detected:

```python
from apywire import CircularWiringError, Wiring

spec = {
    "MyClass a": {"dep": "{b}"},
    "MyClass b": {"dep": "{a}"},
}

wired = Wiring(spec)
try:
    obj = wired.a()
except CircularWiringError as e:
    print(f"Circular dependency: {e}")
```

### UnknownPlaceholderError

::: apywire.UnknownPlaceholderError
    options:
      show_source: false

Raised when a placeholder references a non-existent object:

```python
from apywire import UnknownPlaceholderError, Wiring

spec = {
    "MyClass obj": {"dep": "{nonexistent}"},
}

wired = Wiring(spec)
try:
    obj = wired.obj()
except UnknownPlaceholderError as e:
    print(f"Unknown placeholder: {e}")
```

### LockUnavailableError

::: apywire.LockUnavailableError
    options:
      show_source: false

Raised in thread-safe mode when a lock cannot be acquired after maximum retry attempts:

```python
from apywire import LockUnavailableError, Wiring

wired = Wiring(spec, thread_safe=True, max_lock_attempts=1)

try:
    obj = wired.my_object()
except LockUnavailableError as e:
    print(f"Could not acquire lock: {e}")
```

## Usage Examples

### Basic Wiring

```python
from apywire import Wiring

spec = {
    "datetime.datetime now": {"year": 2025, "month": 1, "day": 1},
}

wired = Wiring(spec)
dt = wired.now()  # datetime.datetime(2025, 1, 1, 0, 0)
```

### Async Access

```python
import asyncio
from apywire import Wiring

async def main():
    wired = Wiring(spec)
    obj = await wired.aio.my_object()

asyncio.run(main())
```

### Thread-Safe Instantiation

```python
from apywire import Wiring

wired = Wiring(spec, thread_safe=True)
# Safe to use across multiple threads
```

### Code Compilation

```python
from apywire import WiringCompiler

compiler = WiringCompiler(spec)
code = compiler.compile(aio=True, thread_safe=True)

with open("compiled_wiring.py", "w") as f:
    f.write(code)
```

### Generator (Spec Generator)

```python
from apywire import Generator, Wiring

# Generate a spec from a class signature
spec = Generator.generate("myapp.models.Simple now")

# Override a generated default if needed
spec["now_year"] = 2025

wired = Wiring(spec)
now = wired.now()
```

## See Also

- **[Getting Started](getting-started.md)** - Quick start guide
- **[User Guide](user-guide/index.md)** - Comprehensive usage documentation
- **[Examples](examples.md)** - Practical examples and patterns
