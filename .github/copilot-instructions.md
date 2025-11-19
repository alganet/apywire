<!--
SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>

SPDX-License-Identifier: ISC
-->
# AI Coding Guidelines for apywire

## Overview
apywire is a Python library for object wiring with lazy loading. It provides dependency injection through spec-based configuration and code generation.

## Architecture
- **Core Components**: `Wired` class (lazy container), `wire()` (factory), `compile()` (code generator)
- **Data Flow**: Spec dict → `_parse_spec()` → ParsedSpec → `Wired.__init__()` → lazy `__getattr__()` → instantiate with `**value`
- **Key Patterns**: Generic with `TypeVar T` for value types, lazy loading via `__getattr__`, spec parsing with module/class resolution
- **Equivalence Goal**: `compile()` and `wire()` produce equivalent behavior - compiled code should match wired object functionality
- **Config-Friendly Specs**: Specs are designed to be easily serializable from YAML/JSON

## Developer Workflows
- **Full Check**: `make all` (format, lint, test coverage)
- **Build & Publish**: `make dist` (ensures dist/), `make publish` (uploads to PyPI)
- **Clean**: `make clean` (removes dist/, __pycache__, .coverage, etc.)
- **Debug**: Use `pytest -xvs` for verbose test runs

## Conventions
- **Typing**: Strict mypy with `disallow_any_* = true`, use `object` over `Any`
- **Formatting**: 79 char lines with black/isort
- **Licensing**: SPDX headers on all files, REUSE compliance
- **Coverage**: 95% required, test edge cases like `AttributeError` in `__getattr__`
- **Structure**: Type aliases in wiring.py, Makefile-driven development

## Examples
- **Lazy Access**: `wired = wire(spec); obj = wired.someName` (instantiates on first access)
- **Spec Format**: `{"module.Class name": {"param": "value"}}` (YAML/JSON-compatible structure)
- **Equivalence**: `compile(spec)` generates code that behaves identically to `wire(spec)`

## Key Files
- `apywire/wiring.py`: Core implementation
- `Makefile`: All dev commands
- `pyproject.toml`: Dependencies and config
- `tests/test_simple.py`: Usage examples