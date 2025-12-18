<!--
SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>

SPDX-License-Identifier: ISC
-->

# Development

Contributing guide for apywire developers.

## Getting Started

### Prerequisites

- Python 3.12 or later
- Git
- Make (optional but recommended)

### Initial Setup

Clone the repository and set up your development environment:

```bash
git clone https://github.com/alganet/apywire.git
cd apywire

# Install dev dependencies
uv sync --extra dev
```

This will:
1. Create (or update) a `.venv` project environment
2. Install all development dependencies including mkdocs, pytest, mypy, etc.

## Development Workflow

### Running Tests

```bash
# Run all tests with pytest
make test

# Run tests with coverage
make coverage

# Run verbose tests
pytest -xvs
```

The project enforces 95% test coverage or higher. New code should include comprehensive tests.

### Code Formatting

The project uses `black` and `isort` for code formatting:

```bash
# Format all code
make format
```

This command:
1. Runs `reuse annotate` to add SPDX headers
2. Formats code with `black` (79-character line length)
3. Sorts imports with `isort`

### Linting

```bash
# Run all linters
make lint
```

This runs:
1. `reuse lint` - Validates SPDX licensing headers
2. `flake8` - Python style checker
3. `mypy` - Static type checker

All linting must pass before submitting a pull request.

### Building

```bash
# Build Cython extension
make build

# Build distribution packages
make dist
```

The build process compiles `apywire/wiring.py` to C using Cython for performance.

### Complete Check

Run all checks before committing:

```bash
make all
```

This runs: `format` → `lint` → `coverage` → `build`

## Project Structure

```
apywire/
├── apywire/              # Main package
│   ├── __init__.py       # Public API exports
│   ├── wiring.py         # Base wiring functionality
│   ├── runtime.py        # Runtime wiring implementation
│   ├── compiler.py       # Code generation
│   ├── threads.py        # Thread safety utilities
│   ├── exceptions.py     # Exception classes
│   ├── constants.py      # Constants and configuration
│   └── py.typed          # PEP 561 marker file
├── tests/                # Test suite
│   ├── test_single.py    # Runtime tests
│   ├── test_compile_aio.py  # Async compilation tests
│   ├── test_threading.py    # Thread safety tests
│   ├── test_factory_methods.py  # Factory method tests
│   ├── test_edge_cases.py   # Edge case tests
│   ├── test_stdlib_compat.py  # Stdlib compatibility tests
│   └── test_internals.py    # Internal implementation tests
├── docs/                 # MkDocs documentation
├── pyproject.toml        # Project configuration
├── setup.py              # Build configuration (Cython)
├── Makefile              # Development commands
└── README.md             # Project readme
```

## Code Standards

### Type Annotations

apywire uses **strict mypy** with very aggressive settings:

```toml
[tool.mypy]
strict = true
disallow_any_unimported = true
disallow_any_decorated = true
disallow_any_explicit = true
disallow_subclassing_any = true
disallow_any_expr = true
warn_return_any = true
```

Guidelines:
- **No `Any`**: Use `object` instead
- Full type annotations on all functions and methods
- Type all variables where type can't be inferred
- Use type aliases for complex types

Example:

```python
from typing import TypeAlias

# Good
def process(data: dict[str, str]) -> list[str]:
    return list(data.values())

# Bad - missing return type
def process(data: dict[str, str]):
    return list(data.values())
```

### Code Style

- **Line length**: 79 characters (enforced by `black`)
- **Imports**: Sorted with `isort`, profile `black`
- **Docstrings**: Google style
- **Naming**:
  - Classes: `PascalCase`
  - Functions/methods: `snake_case`
  - Constants: `UPPER_CASE`
  - Private: `_leading_underscore`

### SPDX Licensing

All source files must have SPDX headers:

```python
# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC
```

Run `make format` to automatically add headers to new files.

## Architecture

### Core Concepts

#### Lazy Loading

Objects are instantiated via `__getattr__` only when accessed:

```python
def __getattr__(self, name: str):
    if name in self._values:
        return Accessor(lambda: self._values[name])
    # Instantiate and cache...
```

#### Placeholder Resolution

Strings like `{name}` are converted to `_WiredRef` markers during parsing:

```python
class _WiredRef:
    __slots__ = ("name",)

def _resolve(self, obj):
    if isinstance(obj, str) and self._is_placeholder(obj):
        return _WiredRef(ref_name)
    return obj
```

At instantiation time, `_WiredRef` markers are resolved to actual objects.

#### Thread Safety

Thread-safe mode uses:
1. **Per-attribute locks**: `dict[str, threading.Lock]`
2. **Global fallback lock**: Single `threading.Lock`
3. **Thread-local state**: For circular dependency detection

See `apywire/threads.py` for details.

#### Compilation

The compiler generates Python code that:
1. Imports all required modules
2. Creates a `Compiled` class
3. Generates accessor methods for each wired object
4. Optionally includes async accessors and thread safety

See `apywire/compiler.py` for the implementation.

### Module Responsibilities

- **`wiring.py`**: Base class, type system, placeholder parsing
- **`runtime.py`**: Runtime `Wiring` implementation, `Accessor`/`AioAccessor`
- **`compiler.py`**: Code generation via `WiringCompiler`
- **`threads.py`**: Thread safety mixins and utilities
- **`exceptions.py`**: Custom exception classes
- **`constants.py`**: Shared constants (delimiter, placeholder markers)

## Testing

### Test Organization

- **`test_single.py`**: Runtime wiring tests (non-thread-safe)
- **`test_threading.py`**: Thread-safe wiring tests
- **`test_compile_aio.py`**: Async compilation tests
- **`test_factory_methods.py`**: Factory method tests
- **`test_edge_cases.py`**: Edge cases and error handling
- **`test_stdlib_compat.py`**: Standard library integration
- **`test_internals.py`**: Internal implementation details

### Writing Tests

Test naming convention:

```python
def test_<feature>_<scenario>_<expected_behavior>():
    """Brief description of what is being tested."""
    # Arrange
    spec = {...}

    # Act
    wired = Wiring(spec)
    result = wired.something()

    # Assert
    assert result == expected
```

Always test:
1. Runtime behavior
2. Compiled behavior (when applicable)
3. Async variants (when applicable)
4. Thread-safe variants (when applicable)
5. Error cases

### Coverage

Target: **95% branch coverage or higher**

Check coverage:

```bash
make coverage
```

View HTML coverage report:

```bash
open htmlcov/index.html
```

## Documentation

### Building Docs

```bash
# Serve docs locally
make docs-serve

# Build static site
make docs-build
```

### Writing Documentation

- Use **GitHub Flavored Markdown**
- Include code examples that actually work
- Add SPDX headers to all `.md` files
- Use admonitions for important notes:

```markdown
!!! note
    This is a note

!!! warning
    This is a warning
```

## Pull Request Process

1. **Create a branch** from `main`:
   ```bash
   git checkout -b feature/my-feature
   ```

2. **Make changes** and ensure tests pass:
   ```bash
   make all
   ```

3. **Commit changes** with descriptive messages:
   ```bash
   git commit -m "Add feature X to handle Y"
   ```

4. **Push to GitHub**:
   ```bash
   git push origin feature/my-feature
   ```

5. **Create pull request** on GitHub

6. **Address review feedback** if any

## Release Process

(For maintainers)

1. Update version in `pyproject.toml`
2. Update CHANGELOG (if present)
3. Run full test suite: `make all`
4. Build distribution: `make dist`
5. Tag release: `git tag v0.x.x`
6. Push tag: `git push origin v0.x.x`
7. Publish to PyPI: `make publish`

## Getting Help

- **Issues**: [GitHub Issues](https://github.com/alganet/apywire/issues)
- **Discussions**: [GitHub Discussions](https://github.com/alganet/apywire/discussions)
- **Documentation**: [Full Documentation](https://github.com/alganet/apywire)

## License

apywire is licensed under the ISC License. See [LICENSE](https://github.com/alganet/apywire/blob/main/LICENSES/ISC.txt) for details.

## Next Steps

- **[API Reference](api-reference.md)** - Detailed API documentation
- **[User Guide](user-guide/index.md)** - Learn how to use apywire
- **[Examples](examples.md)** - Practical examples
