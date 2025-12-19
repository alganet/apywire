<!--
SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>

SPDX-License-Identifier: ISC
-->

# Basic Usage

This guide covers the fundamental usage patterns of apywire.

## Creating a Wiring Container

The `Wiring` class is the main entry point for dependency injection:

```python
from apywire import Wiring

spec = {
    "datetime.datetime now": {"year": 2025, "month": 1, "day": 1},
}

wired = Wiring(spec)
```

By default, `Wiring` creates a non-thread-safe container suitable for single-threaded applications. For thread safety, see the [Thread Safety](thread-safety.md) guide.

## Defining Specs

The spec dictionary maps wiring keys to configuration. There are two types of entries:

### Wired Objects

Use the format `"module.Class name"` to define objects that should be lazily instantiated:

```python
spec = {
    "datetime.datetime start_time": {"year": 2025, "month": 1, "day": 1},
    "pathlib.Path project_root": {0: "/home/user/project"},
    "MyClass service": {"param1": "value1", "param2": 42},
}
```

### Constants

Simple keys without the `module.Class` format become constants:

```python
spec = {
    "host": "localhost",
    "port": 8080,
    "debug": True,
    "api_key": "secret-key-here",
}

wired = Wiring(spec)
# Constants are primarily used as placeholder references in other wired objects
```

!!! note
    Constants are most useful as placeholder references for other wired objects using the `{name}` syntax.

## Spec Value Types

apywire supports various parameter types:

### Keyword Arguments (Dict)

```python
spec = {
    "datetime.datetime dt": {
        "year": 2025,
        "month": 6,
        "day": 15,
        "hour": 10,
    },
}
```

### Positional Arguments (List)

```python
spec = {
    "pathlib.Path path": ["/home/user/project"],
}
```

### Positional Arguments (Numeric Dict Keys)

```python
spec = {
    "pathlib.Path path": {0: "/home", 1: "user", 2: "project"},
}
```

### Mixed Arguments

You can combine positional and keyword arguments:

```python
spec = {
    "MyClass obj": {
        0: "positional_arg1",
        1: "positional_arg2",
        "keyword_arg": "value",
    },
}
```

Numeric keys are sorted and passed as positional arguments, while string keys become keyword arguments.

## Using Placeholders

Reference other wired objects or constants using `{name}` syntax:

```python
spec = {
    "database_url": "postgresql://localhost/mydb",
    "max_connections": 10,

    "psycopg2.pool.SimpleConnectionPool pool": {
        "minconn": 1,
        "maxconn": "{max_connections}",
        "dsn": "{database_url}",
    },
}

wired = Wiring(spec)
pool = wired.pool()  # placeholders are resolved to actual values
```

### Nested Placeholders

Placeholders work in nested structures:

```python
spec = {
    "api_key": "secret-key",

    "MyClient client": {
        "config": {
            "auth": {
                "api_key": "{api_key}",  # Nested placeholder
            },
            "timeout": 30,
        },
    },
}
```

### List Placeholders

Placeholders work in lists too:

```python
spec = {
    "datetime.datetime start": {"year": 2025, "month": 1, "day": 1},
    "datetime.datetime end": {"year": 2025, "month": 12, "day": 31},

    "MyReport report": {
        "date_range": ["{start}", "{end}"],  # List with placeholders
    },
}
```

## Accessing Wired Objects

### The Accessor Pattern

When you access an attribute on a `Wiring` container, you get an `Accessor`:

```python
from apywire import Wiring, Accessor

wired = Wiring(spec)
accessor = wired.my_object  # Returns an Accessor instance
print(type(accessor))  # <class 'apywire.runtime.Accessor'>
```

Call the accessor to instantiate the object:

```python
obj = accessor()  # Instantiates the object
```

Most commonly, you'll do both in one line:

```python
obj = wired.my_object()
```

### Caching Behavior

Objects are instantiated once and cached:

```python
spec = {
    "datetime.datetime now": {"year": 2025, "month": 1, "day": 1},
}

wired = Wiring(spec)

dt1 = wired.now()
dt2 = wired.now()

assert dt1 is dt2  # True - same object instance!
```

Each access returns the **same instance**, not a new one. This is crucial for:

- Maintaining singleton-like behavior
- Avoiding duplicate resource allocation (e.g., database connections)
- Ensuring consistent state across your application

### When Instantiation Happens

```python
wired = Wiring(spec)
# No objects instantiated yet!

accessor = wired.my_object
# Still nothing instantiated - just got the accessor

obj = accessor()
# NOW the object is created and cached
```

## Working with Multiple Objects

```python
spec = {
    "datetime.datetime start": {"year": 2025, "month": 1, "day": 1},
    "datetime.timedelta delta": {"days": 7},
    "pathlib.Path root": ["/home/user"],
}

wired = Wiring(spec)

# Access multiple objects
start_date = wired.start()
time_delta = wired.delta()
root_path = wired.root()
```

## Dependency Resolution Order

When accessing an object with placeholder dependencies, apywire resolves them in order:

```python
spec = {
    "MyDatabase db": {},
    "MyCache cache": {"db": "{db}"},  # Depends on db
    "MyService service": {
        "cache": "{cache}",  # Depends on cache
        "db": "{db}",        # Also depends on db
    },
}

wired = Wiring(spec)
service = wired.service()
# Resolution order: db → cache → service
```

apywire automatically handles the dependency graph and instantiates objects in the correct order.

## Error Handling

### Unknown Placeholder

```python
from apywire import Wiring, UnknownPlaceholderError

spec = {
    "MyClass obj": {"dependency": "{nonexistent}"},
}

wired = Wiring(spec)
try:
    obj = wired.obj()
except UnknownPlaceholderError as e:
    print(f"Unknown placeholder: {e}")
```

### Circular dependencies

See [Circular dependencies](user-guide/circular-dependencies.md) for examples, expected exceptions, and advice to avoid cycles.

### Import Errors

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

## Best Practices

### 1. Use Descriptive Names

```python
# Good
spec = {
    "psycopg2.connect db_connection": {"dsn": "{database_url}"},
    "MyRepository user_repository": {"db": "{db_connection}"},
}

# Avoid
spec = {
    "psycopg2.connect conn": {"dsn": "{url}"},
    "MyRepository repo": {"db": "{conn}"},
}
```

### 2. Group Related Objects

```python
spec = {
    # Database layer
    "db_url": "postgresql://localhost/mydb",
    "psycopg2.connect db": {"dsn": "{db_url}"},

    # Cache layer
    "redis_url": "redis://localhost",
    "redis.Redis cache": {"url": "{redis_url}"},

    # Service layer
    "MyService service": {"db": "{db}", "cache": "{cache}"},
}
```

### 3. Validate Configuration Early

```python
def validate_wiring(wired: Wiring) -> None:
    """Validate all wired objects can be instantiated."""
    # Access all objects to trigger any configuration errors
    _ = wired.database()
    _ = wired.cache()
    _ = wired.service()

# In your app startup
wired = Wiring(spec)
validate_wiring(wired)  # Fail fast if configuration is wrong
```

### 4. Use Constants for Configuration

```python
spec = {
    # Configuration constants
    "debug": True,
    "log_level": "INFO",
    "timeout": 30,

    # Wired objects using configuration
    "logging.Logger logger": {
        "name": "myapp",
        "level": "{log_level}",
    },
    "MyClient client": {
        "timeout": "{timeout}",
        "debug": "{debug}",
    },
}
```

### 5. Keep Specs Testable

```python
# production_spec.py
def get_production_spec():
    return {
        "psycopg2.connect db": {"dsn": "postgresql://prod/db"},
    }

# test_spec.py
def get_test_spec():
    return {
        "unittest.mock.Mock db": {},  # Mock database for testing
    }

# Usage
if os.getenv("TESTING"):
    wired = Wiring(get_test_spec())
else:
    wired = Wiring(get_production_spec())
```

## Next Steps

- **[Async Support](async-support.md)** - Use `await wired.aio.name()` for async access
- **[Thread Safety](thread-safety.md)** - Enable thread-safe instantiation
- **[Compilation](compilation.md)** - Generate standalone code from your spec
- **[Advanced Features](advanced.md)** - Factory methods and complex patterns
