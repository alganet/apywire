<!--
SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>

SPDX-License-Identifier: ISC
-->

# Advanced Features

This guide covers advanced apywire features and patterns for complex use cases.

## Factory Methods

apywire supports class factory methods (classmethods and staticmethods) using the syntax `module.Class name.factory_method`.

### Basic Factory Method

```python
import datetime
from apywire import Wiring

spec = {
    "datetime.datetime dt.fromtimestamp": {
        0: 1234567890,  # Unix timestamp
    },
}

wired = Wiring(spec)
dt = wired.dt()  # datetime.datetime.fromtimestamp(1234567890)
```

### With Keyword Arguments

```python
spec = {
    "datetime.datetime dt.fromisoformat": {
        "date_string": "2025-01-01T12:00:00",
    },
}

wired = Wiring(spec)
dt = wired.dt()  # datetime.datetime.fromisoformat("2025-01-01T12:00:00")
```

### Custom Factory Methods

```python
class Product:
    def __init__(self, name: str, price: float):
        self.name = name
        self.price = price

    @classmethod
    def from_dict(cls, data: dict):
        return cls(name=data["name"], price=data["price"])

spec = {
    "mymodule.Product product.from_dict": {
        "data": {"name": "Widget", "price": 19.99},
    },
}
```

### With Placeholders

```python
spec = {
    "mymodule.Config config": {"value": "production"},
    "mymodule.Service service.from_config": {
        "cfg": "{config}",  # Reference to config object
    },
}
```

### Static Methods

Factory methods can be staticmethods too:

```python
class Calculator:
    def __init__(self, result: int):
        self.result = result

    @staticmethod
    def create_with_sum(a: int, b: int):
        return Calculator(result=a + b)

spec = {
    "mymodule.Calculator calc.create_with_sum": {
        "a": 10,
        "b": 20,
    },
}

wired = Wiring(spec)
calc = wired.calc()
assert calc.result == 30
```

!!! warning "Nested Factory Methods Not Supported"
    ```python
    # ❌ This will raise ValueError
    spec = {
        "datetime.datetime dt.method1.method2": {},
    }
    ```

    Nested factory methods are not supported. Only one level is allowed: `name.factory_method`.

## Positional Arguments

apywire supports positional arguments in three ways:

### Using Lists

```python
spec = {
    "pathlib.Path path": ["/home", "user", "project"],
}

wired = Wiring(spec)
path = wired.path()  # pathlib.Path("/home", "user", "project")
```

### Using Numeric Dict Keys

```python
spec = {
    "pathlib.Path path": {
        0: "/home",
        1: "user",
        2: "project",
    },
}
```

Keys are sorted numerically and passed as positional arguments.

### Mixed Positional and Keyword Args

```python
spec = {
    "datetime.datetime dt": {
        0: 2025,  # year (positional)
        1: 1,     # month (positional)
        2: 1,     # day (positional)
        "hour": 12,     # keyword argument
        "minute": 30,   # keyword argument
    },
}

wired = Wiring(spec)
dt = wired.dt()  # datetime.datetime(2025, 1, 1, hour=12, minute=30)
```

## Complex Nested Dependencies

### Deep Dependency Chains

```python
spec = {
    "DatabaseConfig db_config": {},
    "Database db": {"config": "{db_config}"},
    "CacheLayer cache": {"db": "{db}"},
    "RepositoryLayer repo": {
        "db": "{db}",
        "cache": "{cache}",
    },
    "ServiceLayer service": {
        "repo": "{repo}",
        "cache": "{cache}",
    },
}

wired = Wiring(spec)
service = wired.service()
# Resolves: db_config → db → cache → repo → service
```

### Nested Data Structures

Placeholders work in nested dicts, lists, and tuples:

```python
spec = {
    "api_key": "secret-key-123",
    "timeout": 30,

    "MyClient client": {
        "config": {
            "auth": {
                "type": "bearer",
                "token": "{api_key}",  # Nested in dict
            },
            "options": {
                "timeout": "{timeout}",
                "retries": 3,
            },
        },
        "endpoints": [
            "https://api1.example.com",
            "https://api2.example.com",
        ],
    },
}
```

### Multiple References to Same Object

```python
spec = {
    "Logger logger": {},
    "ServiceA svc_a": {"logger": "{logger}"},
    "ServiceB svc_b": {"logger": "{logger}"},
    "Coordinator coord": {
        "logger": "{logger}",
        "services": ["{svc_a}", "{svc_b}"],
    },
}

wired = Wiring(spec)
coord = wired.coord()

# All services share the same logger instance
assert coord.logger is coord.services[0].logger
assert coord.logger is coord.services[1].logger
```

## Error Handling

### CircularWiringError

Raised when a circular dependency is detected:

```python
from apywire import CircularWiringError

spec = {
    "MyClass a": {"dependency": "{b}"},
    "MyClass b": {"dependency": "{a}"},  # Circular!
}

wired = Wiring(spec)
try:
    obj = wired.a()
except CircularWiringError as e:
    print(f"Circular dependency: {e}")
    # Error message shows the dependency chain
```

The error message includes the full resolution chain:

```
Circular dependency detected while resolving 'a':
  a -> b -> a
```

### UnknownPlaceholderError

Raised when a placeholder references a non-existent object:

```python
from apywire import UnknownPlaceholderError

spec = {
    "MyClass obj": {"dependency": "{nonexistent}"},
}

wired = Wiring(spec)
try:
    obj = wired.obj()
except UnknownPlaceholderError as e:
    print(f"Unknown placeholder: {e}")
```

### LockUnavailableError

Raised in thread-safe mode when a lock cannot be acquired:

```python
from apywire import LockUnavailableError

wired = Wiring(spec, thread_safe=True, max_lock_attempts=1)

try:
    obj = wired.my_object()
except LockUnavailableError as e:
    print(f"Lock contention: {e}")
```

This is rare and usually indicates extreme contention or a configuration issue.

### Import Errors

If a module or class can't be imported, a standard `ImportError` is raised:

```python
spec = {
    "nonexistent.module.Class obj": {},
}

wired = Wiring(spec)
try:
    obj = wired.obj()
except ImportError as e:
    print(f"Cannot import: {e}")
```

### Attribute Errors

If a class doesn't have the specified factory method:

```python
spec = {
    "datetime.datetime dt.nonexistent_method": {},
}

wired = Wiring(spec)
try:
    dt = wired.dt()
except AttributeError as e:
    print(f"Method not found: {e}")
```

## Standard Library Compatibility

apywire works with Python standard library classes:

### datetime

```python
spec = {
    "datetime.datetime now.fromtimestamp": {0: 1234567890},
    "datetime.timedelta duration": {"days": 7, "hours": 12},
    "datetime.date today.fromisoformat": {"date_string": "2025-01-01"},
}
```

### pathlib

```python
spec = {
    "pathlib.Path root": ["/home/user"],
    "pathlib.Path project": {0: "/home/user/project"},
}
```

### collections

```python
spec = {
    "collections.Counter counter": [["a", "b", "a", "c", "b", "a"]],
    "collections.defaultdict dd": {"default_factory": list},
}
```

### threading

```python
spec = {
    "threading.Lock lock": {},
    "threading.Event event": {},
    "threading.Semaphore sem": {0: 5},
}
```

## Dynamic Spec Building

Build specs programmatically:

```python
def build_spec(env: str) -> dict:
    """Build spec based on environment."""
    spec = {
        "log_level": "DEBUG" if env == "dev" else "INFO",
    }

    if env == "production":
        spec["database_url"] = "postgresql://prod-server/db"
    else:
        spec["database_url"] = "sqlite:///dev.db"

    spec["MyDatabase db"] = {"url": "{database_url}"}

    return spec

# Usage
import os
env = os.getenv("APP_ENV", "dev")
wired = Wiring(build_spec(env))
```

## Testing Patterns

### Mock Dependencies

Replace real dependencies with mocks for testing:

```python
# production_spec.py
production_spec = {
    "psycopg2.connect db": {"dsn": "postgresql://prod/db"},
    "redis.Redis cache": {"url": "redis://prod"},
}

# test_spec.py
from unittest.mock import Mock

test_spec = {
    "unittest.mock.Mock db": {},  # Mock database
    "unittest.mock.Mock cache": {},  # Mock cache
}

# In tests
def test_my_app():
    wired = Wiring(test_spec)
    # All dependencies are mocks
```

### Spec Fixtures

Use pytest fixtures for common specs:

```python
import pytest
from apywire import Wiring

@pytest.fixture
def wired():
    spec = {
        "MyDatabase db": {},
        "MyCache cache": {},
        "MyService service": {
            "db": "{db}",
            "cache": "{cache}",
        },
    }
    return Wiring(spec)

def test_service(wired):
    service = wired.service()
    assert service is not None
```

## Best Practices

### 1. Use Type Aliases for Complex Specs

```python
from typing import TypeAlias
from apywire import Spec

DatabaseSpec: TypeAlias = Spec

def get_database_spec() -> DatabaseSpec:
    return {
        "database_url": "postgresql://localhost/db",
        "psycopg2.connect connection": {"dsn": "{database_url}"},
    }
```

### 2. Validate Specs Early

```python
def validate_spec(wired: Wiring) -> None:
    """Validate all wired objects can be instantiated."""
    # Try to access all known objects
    _ = wired.database()
    _ = wired.cache()
    _ = wired.service()

# Fail fast at application startup
wired = Wiring(spec)
validate_spec(wired)
```

### 3. Document Complex Dependencies

```python
spec = {
    # Core infrastructure
    "database_url": "postgresql://localhost/db",
    "psycopg2.connect db": {"dsn": "{database_url}"},

    # Caching layer (depends on db)
    "MyCache cache": {"db": "{db}"},

    # Business logic (depends on db and cache)
    "MyService service": {
        "db": "{db}",
        "cache": "{cache}",
    },
}
```

### 4. Separate Concerns

```python
# config.py - Configuration constants
config_spec = {
    "host": "localhost",
    "port": 8080,
    "debug": True,
}

# infrastructure.py - Infrastructure components
infra_spec = {
    "Database db": {"host": "{host}", "port": "{port}"},
    "Cache cache": {},
}

# services.py - Business logic
service_spec = {
    "MyService service": {"db": "{db}", "cache": "{cache}"},
}

# Merge them
full_spec = {**config_spec, **infra_spec, **service_spec}
wired = Wiring(full_spec)
```

### 5. Use Constants for Configuration

Constants now support placeholder expansion, making configuration more maintainable:

```python
spec = {
    # Configuration constants
    "db_host": "localhost",
    "db_port": 5432,
    "db_name": "myapp",

    # Build connection string from constants (immediate expansion)
    "db_url": "postgresql://{db_host}:{db_port}/{db_name}",

    # Use in wired object
    "psycopg2.connect db": {"dsn": "{db_url}"},
}
```

For environment-based configuration:

```python
import os

spec = {
    "db_host": os.getenv("DB_HOST", "localhost"),
    "db_port": int(os.getenv("DB_PORT", "5432")),
    "db_name": os.getenv("DB_NAME", "myapp"),

    # Placeholder expansion keeps spec clean
    "db_url": "postgresql://{db_host}:{db_port}/{db_name}",
    "psycopg2.connect db": {"dsn": "{db_url}"},
}
```

See [Configuration Files](configuration-files.md#placeholder-expansion) for more details.

## Performance Tips

### 1. Lazy Loading is Your Friend

Objects are only created when accessed, so define everything in your spec:

```python
spec = {
    "ExpensiveResource resource1": {},  # Won't be created unless accessed
    "ExpensiveResource resource2": {},  # Same here
    "QuickResource quick": {},
}

wired = Wiring(spec)
quick = wired.quick()  # Only this is instantiated
```

### 2. Cache is Per-Container

Each `Wiring` instance has its own cache:

```python
# ✅ Good: Single container, shared cache
wired = Wiring(spec)
obj1 = wired.resource()  # Created
obj2 = wired.resource()  # Cached

# ❌ Avoid: Multiple containers, no sharing
wired1 = Wiring(spec)
wired2 = Wiring(spec)
obj1 = wired1.resource()  # Created
obj2 = wired2.resource()  # Created again!
```

### 3. Use Compilation for Production

Compiled code is slightly faster:

```python
# Development: runtime
wired = Wiring(spec)

# Production: compiled
compiler = WiringCompiler(spec)
code = compiler.compile()
# Save to file, import in production
```

### 4. Thread Safety Has Overhead

Only enable when needed:

```python
# Single-threaded: fast
wired = Wiring(spec, thread_safe=False)

# Multi-threaded: slight overhead
wired = Wiring(spec, thread_safe=True)
```

## Next Steps

- **[API Reference](../api-reference.md)** - Complete API documentation
- **[Examples](../examples.md)** - Practical examples and patterns
- **[Development](../development.md)** - Contributing guide
