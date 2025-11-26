<!--
SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>

SPDX-License-Identifier: ISC
-->

# apywire Documentation

Welcome to the apywire documentation! apywire is a powerful, flexible dependency injection library for Python 3.12+ that makes managing object dependencies simple and elegant.

## What is apywire?

apywire provides **lazy object wiring** through a clean, declarative specification format. Instead of manually instantiating objects and passing dependencies around, you define a `spec` that describes what you need, and apywire handles the rest.

```python
from apywire import Wiring

# Define what you want
spec = {
    "datetime.datetime now": {"year": 2025, "month": 1, "day": 1},
    "MyService service": {"start_time": "{now}"},  # Reference other objects
}

# Get what you need
wired = Wiring(spec)
service = wired.service()  # Dependencies resolved automatically
```

## Key Features

### 🚀 Lazy Loading
Objects are instantiated **only when accessed**, not when you create the container. This improves startup performance and lets you define everything upfront without overhead.

### ⚡ Async Support
Built-in `async/await` support via `AioAccessor`. Use `await wired.aio.my_object()` for asynchronous object access without blocking the event loop.

### 🔒 Thread Safety
Optional thread-safe instantiation using optimistic locking. Enable with `thread_safe=True` for multi-threaded applications.

### 📦 Code Generation
Compile your specs to standalone Python code with `WiringCompiler(spec).compile()`. Deploy generated code for better performance and simpler dependency management.

### 📄 Naturally Configurable
Load specs from YAML, TOML, JSON, or INI files. Keep configuration separate from code, support multiple environments, and let non-developers manage settings. Constants can reference other constants using `{name}` placeholders for flexible configuration.

### 🎯 Zero Dependencies
No external runtime dependencies. apywire works with just Python 3.12+ standard library.

## Why Choose apywire?

### Clean, Declarative Configuration
Define your entire dependency graph in a single, readable dictionary. No decorators, no magic imports, just plain Python data structures.

### Perfect for Layered Architectures
Ideal for applications with clear separation of concerns: database layer, service layer, API layer. Wire them together without tight coupling.

### Flexible Deployment Options
- **Development**: Use runtime `Wiring` for fast iteration
- **Production**: Compile to standalone code for deployment
- **Testing**: Easily swap real dependencies for mocks
- **Configuration**: Load specs from YAML, TOML, JSON, or INI files

### Production-Ready
- Strict mypy type checking throughout
- 95% test coverage or higher enforced
- Support for async, threading, and edge cases
- No external dependencies to manage

### Use Cases
- **Web Applications**: FastAPI, Flask, Django services
- **Microservices**: Service-to-service communication setup
- **CLI Tools**: Complex command-line applications with many dependencies
- **Data Pipelines**: ETL processes with configurable components
- **Testing**: Mock injection for comprehensive test coverage

### Dependency Injection via Placeholders

Reference other wired objects using `{name}` placeholders:

```python
spec = {
    "datetime.datetime base_time": {"year": 2025, "month": 1, "day": 1},
    "datetime.timedelta offset": {"days": 7},
    "MyClass processor": {
        "start_time": "{base_time}",
        "delta": "{offset}",
    },
}
```

### Async Support

Access objects asynchronously in async contexts:

```python
async def main():
    wired = Wiring(spec)
    obj = await wired.aio.my_object()  # Async access
```

### Thread-Safe Instantiation

Enable thread safety for multi-threaded applications:

```python
wired = Wiring(spec, thread_safe=True)
# Safe to use across multiple threads
```

### Code Compilation

Generate standalone Python code from your wiring spec:

```python
from apywire import WiringCompiler

compiler = WiringCompiler(spec)
code = compiler.compile(aio=True, thread_safe=True)
# Returns Python code that behaves identically to the runtime container
```

## Next Steps

- [Getting Started](getting-started.md) - Detailed installation and setup guide
- [User Guide](user-guide/index.md) - Comprehensive usage documentation
- [API Reference](api-reference.md) - Complete API documentation
- [Examples](examples.md) - Practical use cases and patterns
- [Development](development.md) - Contributing guide for developers

## License

apywire is licensed under the ISC License. See the [LICENSE](https://github.com/alganet/apywire/blob/main/LICENSES/ISC.txt) file for details.
