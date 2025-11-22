<!--
SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>

SPDX-License-Identifier: ISC
-->
# AI Coding Guidelines for apywire

## Overview
apywire is a Python 3.12+ library for lazy object wiring and dependency injection. It uses spec-based configuration to instantiate objects on-demand with support for async access, thread safety, and code generation via Cython compilation.

## Core API
- **`Wiring(spec, thread_safe=False)`**: Main container for lazy instantiation from a spec dict
- **`wired.name()`**: Returns callable `Accessor` that instantiates object on invocation
- **`await wired.aio.name()`**: Async access via `AioAccessor` using `run_in_executor`
- **`wired.compile(aio=False, thread_safe=False)`**: Generates equivalent Python code as a `Compiled` class
- **Spec Format**: `{"module.Class name": {"param": "value", "ref": "{otherName}"}}`

## Architecture
- **Lazy Loading**: Objects instantiated via `__getattr__` only when accessed, cached after first use
- **Placeholders**: `{name}` in spec values resolve to other wired objects at instantiation
- **Thread Safety**: Optional `thread_safe=True` uses optimistic per-attribute locking with global fallback via `CompiledThreadSafeMixin`
- **Cython Build**: `setup.py` uses Cython to compile `wiring.py` → `wiring.c` with SPDX headers
- **Equivalence**: Compiled output behaves identically to runtime `Wiring` (lazy, async, thread-safe)

## Development Workflow
- **Setup**: `make .venv && make pip` (venv + install deps)
- **Check**: `make all` (format, lint, coverage, build)
- **Test**: `pytest -xvs` (verbose), `make coverage` (95% required)
- **Build**: `make build` (Cython compile), `make dist` (package)
- **Clean**: `make clean` (remove artifacts/caches)

## Code Standards
- **Typing**: Strict mypy with `disallow_any_*=true`, use `object` not `Any`
- **Style**: 79-char lines, `black` + `isort` formatting
- **Licensing**: SPDX headers required on all files, validate with `make reuse`
- **Tests**: Cover sync, async (`test_compile_aio.py`), threading (`test_threading.py`), edge cases

## Key Components
- `apywire/wiring.py`: `Wiring`, `Accessor`, `AioAccessor`, `compile()` method
- `apywire/thread_safety.py`: `CompiledThreadSafeMixin` with optimistic/global locking
- `apywire/exceptions.py`: `WiringError`, `CircularWiringError`, `UnknownPlaceholderError`, `LockUnavailableError`
- `setup.py`: Cython build config with SPDX header injection

## Examples
```python
# Basic lazy access
wired = Wiring({"datetime.datetime now": {"year": 2025}})
dt = wired.now()  # Instantiated on call, cached

# Async access
obj = await wired.aio.now()

# Thread-safe instantiation
wired = Wiring(spec, thread_safe=True)

# Code generation
code = wired.compile(aio=True, thread_safe=True)
```
