<!--
SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>

SPDX-License-Identifier: ISC
-->

# Getting Started

This guide will help you get up and running with apywire quickly.

## Installation

Install apywire using uv:

```bash
uv pip install apywire
```

apywire requires Python 3.12 or later and has no external runtime dependencies.

### Development Installation

If you want to contribute to apywire or run the tests:

```bash
git clone https://github.com/alganet/apywire.git
cd apywire
uv sync --extra dev
```

## Quick Start

### Basic Wiring

Create a simple wiring configuration to manage object instantiation:

```python
from apywire import Wiring

# Define your wiring spec
spec = {
    "datetime.datetime now": {"year": 2025, "month": 1, "day": 1},
}

# Create the wiring container
wired = Wiring(spec)

# Access the object (instantiated lazily on first call)
dt = wired.now()
print(dt)  # 2025-01-01 00:00:00
```

### Understanding the Spec Format

The wiring spec uses the format: `"module.Class name": {parameters}`

- **`module.Class`**: Full module path and class name
- **`name`**: Attribute name to access the wired object
- **`{parameters}`**: Dictionary or list of constructor parameters

Examples:

```python
spec = {
    # Basic class with keyword arguments
    "datetime.datetime dt": {"year": 2025, "month": 6, "day": 15},

    # Class with positional arguments (using list)
    "pathlib.Path root": ["/home/user"],

    # Class with positional arguments (using numeric dict keys)
    "pathlib.Path project": {0: "/home/user/project"},

    # Constant values (no module.Class prefix)
    "port": 8080,
    "host": "localhost",
}
```

### Using Placeholders

Reference other wired objects using the `{name}` syntax:

```python
from apywire import Wiring

spec = {
    "datetime.datetime start": {"year": 2025, "month": 1, "day": 1},
    "datetime.timedelta delta": {"days": 7},
    "MyScheduler scheduler": {
        "start_time": "{start}",  # References the 'start' object
        "duration": "{delta}",     # References the 'delta' object
    },
}

wired = Wiring(spec)
scheduler = wired.scheduler()  # MyScheduler with injected dependencies
```

### Lazy Loading

Objects are only instantiated when you call the accessor:

```python
wired = Wiring(spec)
# Nothing has been instantiated yet!

obj1 = wired.my_object()  # Now it's created
obj2 = wired.my_object()  # Returns the same cached instance
assert obj1 is obj2  # True - same object!
```

## Core Concepts

### 1. Wiring Container

The `Wiring` class is your main container that holds the spec and manages object instantiation:

```python
from apywire import Wiring

wired = Wiring(spec)
```

### 2. Accessors

When you access an attribute on the `Wiring` container, you get an `Accessor` - a callable that instantiates the object:

```python
accessor = wired.my_object  # Returns an Accessor
obj = accessor()              # Calls the accessor to get the object
# Or in one step:
obj = wired.my_object()
```

### 3. Spec Dictionary

The spec is a dictionary that maps wiring keys to configuration:

- **Wiring keys** with `module.Class name` format create wired objects
- **Simple keys** without a dot+class create constant values

### 4. Dependency Resolution

When you access a wired object:

1. apywire checks if it's already cached
2. If not, it resolves all placeholder references (`{name}`)
3. Imports the module and class
4. Instantiates the object with the resolved parameters
5. Caches it for future access

## Next Steps

Now that you understand the basics, explore more advanced features:

- **[Basic Usage](user-guide/basic-usage.md)** - Detailed usage patterns and examples
- **[Async Support](user-guide/async-support.md)** - Using `await wired.aio.name()` for async access
- **[Thread Safety](user-guide/thread-safety.md)** - Thread-safe instantiation for multi-threaded apps
- **[Compilation](user-guide/compilation.md)** - Generate standalone Python code from your spec
- **[Advanced Features](user-guide/advanced.md)** - Factory methods, positional args, and more
- **[Examples](examples.md)** - Practical use cases and patterns

## Common Patterns

### Configuration Management

```python
spec = {
    "host": "localhost",
    "port": 8080,
    "MyApp app": {
        "host": "{host}",
        "port": "{port}",
    },
}
```

### Database Connection

```python
spec = {
    "db_url": "postgresql://localhost/mydb",
    "psycopg2.connect connection": {"dsn": "{db_url}"},
    "MyRepository repo": {"db": "{connection}"},
}
```

### Service Layer

```python
spec = {
    "MyDatabase db": {},
    "MyCache cache": {},
    "MyService service": {
        "database": "{db}",
        "cache": "{cache}",
    },
}
```
