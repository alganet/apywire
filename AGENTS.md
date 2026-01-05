<!--
SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>

SPDX-License-Identifier: ISC
-->
# AI Coding Guidelines for apywire

For detailed development workflow and standards, see **[docs/development.md](docs/development.md)**.

## Project Context

apywire is a Python 3.12+ library for lazy object wiring and dependency injection. It uses spec-based configuration to instantiate objects on-demand with support for async access, thread safety, and code generation via Cython compilation.

**Core API:**
- **`Wiring(spec, thread_safe=False)`**: Main container for lazy instantiation from a spec dict
- **`wired.name()`**: Returns callable `Accessor` that instantiates object on invocation
- **`await wired.aio.name()`**: Async access via `AioAccessor` using `run_in_executor`
- **`compiler = WiringCompiler(spec)`**: For compiling into python code instead of runtime
- **`code = compiler.compile(aio=True, thread_safe=True)`**: Generate python code for the spec
- **Spec Format**: `{"module.Class name": {"param": "value", "ref": "{otherName}"}}`

## Critical Architectural Patterns

**Lazy Loading via `__getattr__`:**
Objects are instantiated only when accessed, using `__getattr__` to intercept attribute access and return `Accessor` callables that handle instantiation and caching.

**Placeholder Resolution:**
Strings like `{name}` in spec values are converted to `_WiredRef` markers during parsing, then resolved to actual objects at instantiation time. See `constants.py` for delimiter patterns.

**Thread Safety Model:**
Uses optimistic per-attribute locking (`dict[str, threading.Lock]`) with a global fallback lock. Thread-local state stores lock-related per-thread state (mode and held locks) used by the `ThreadSafeMixin`; see `threads.py` for implementation details.

**Compilation Equivalence:**
Generated code must behave identically to runtime `Wiring`. The compiler generates accessor methods that replicate lazy loading, caching, and optional async/thread-safe behavior.

## AI-Specific Development Notes

**Strict Mypy Configuration:**
The project uses extremely strict mypy settings including `disallow_any_expr=true`. Never use `Any`—use `object` instead. All functions need complete type annotations. See [Code Standards](docs/development.md#type-annotations) for details.

**Module Structure:**
- `wiring.py`: Base class `WiringBase`, type system, placeholder parsing
- `runtime.py`: Runtime `Wiring` class with `Accessor`/`AioAccessor`
- `compiler.py`: Code generation via `WiringCompiler`
- `threads.py`: Thread safety mixins and utilities
- `exceptions.py`: Custom exception classes
- `constants.py`: Shared constants (placeholder patterns, delimiters)

**Testing Requirements:**
All changes must maintain 100% branch coverage. Test both runtime and compiled behavior, plus async and thread-safe variants where applicable. Use descriptive test names: `test_<feature>_<scenario>_<expected_behavior>()`.

**Testing Conventions:**
- **Compiled Objects**: Use `wired = execd["compiled"]` from `exec(code, execd)`. Do not instantiate `Compiled` manually.
- **Type Safety**: Use `typing.Protocol` for dynamic/compiled objects. Avoid `Any` and `type: ignore`.
- **Module Mocking**: Use `sys.modules` injection with `try...finally` cleanup for custom classes.
- **Async Tests**: Use `asyncio.run()` explicitly within test functions.

**Common Gotchas:**
- SPDX headers required on all files (run `make format` to auto-add)
- 79-character line limit enforced by `black`
- Compiled output is verified against runtime behavior in tests
- Thread-safe tests use actual threading to verify lock behavior

## Quick Reference

```python
# Basic lazy access
wired = Wiring({"datetime.datetime now": {"year": 2025}})
dt = wired.now()  # Instantiated on call, cached

# Async access
obj = await wired.aio.now()

# Thread-safe instantiation
wired = Wiring(spec, thread_safe=True)

# Code generation
compiler = WiringCompiler(spec)
code = compiler.compile(aio=True, thread_safe=True)
```

**Make Commands:**
- `make all` - Complete check (format, lint, coverage, build)
- `make test` - Run pytest suite
- `make coverage` - Check coverage requirements
- `make lint` - Run reuse, flake8, mypy
- `make format` - Run black, isort, add SPDX headers
