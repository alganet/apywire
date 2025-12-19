<!--
SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>

SPDX-License-Identifier: ISC
-->

# User Guide

Welcome to the apywire user guide! This section provides comprehensive documentation on all features and capabilities of apywire.

## Contents

### [Basic Usage](basic-usage.md)
Learn the fundamentals of using apywire, including creating wiring containers, defining specs, using the Accessor pattern, and understanding caching behavior.

### [Configuration Files](configuration-files.md)
Load specs from YAML, TOML, JSON, or INI files. Mix configuration files with environment variables and implement environment-based configs.

### [Async Support](async-support.md)
Discover how to use apywire in asynchronous contexts with `await wired.aio.name()` for async object access.

### [Thread Safety](thread-safety.md)
Understand thread-safe instantiation, optimistic locking mechanisms, and configuration options for multi-threaded applications.

### [Compilation](compilation.md)
Learn how to generate standalone Python code from your wiring specs using `WiringCompiler` for production deployment and performance optimization.

### [Spec Generation](generator.md)
Quickly scaffold wiring specs from class constructor signatures using `Generator`.

### [Advanced Features](advanced.md)
Explore advanced capabilities including factory methods, positional arguments, complex nested dependencies, error handling, and best practices.

## Overview

apywire is designed around a few core principles:

1. **Lazy Loading**: Objects are instantiated only when accessed, improving startup performance
2. **Dependency Injection**: Use placeholder syntax to express dependencies between objects
3. **Flexibility**: Support for keyword arguments, positional arguments, factory methods, and constants
4. **Type Safety**: Strict mypy typing throughout the library
5. **Performance**: Optional code generation via Cython for production deployments

## Quick Navigation

Looking for something specific?

- **Getting started?** → [Basic Usage](basic-usage.md)
- **Need async?** → [Async Support](async-support.md)
- **Multi-threaded app?** → [Thread Safety](thread-safety.md)
- **Production deployment?** → [Compilation](compilation.md)
- **Complex use cases?** → [Advanced Features](advanced.md)
- **Scaffold specs quickly?** → [Spec Generation](generator.md)

## Common Workflows

### Development

1. Define your wiring spec with dependencies
2. Create a `Wiring` container
3. Access objects via the Accessor pattern
4. Use `thread_safe=False` for single-threaded development

### Production

1. Test your wiring configuration thoroughly
2. Use `WiringCompiler` to generate standalone code
3. Enable `thread_safe=True` if deploying multi-threaded
4. Optionally compile with Cython for maximum performance

### Testing

1. Define test-specific specs with mock objects
2. Use placeholder references to inject test doubles
3. Leverage lazy loading to avoid unnecessary instantiation
4. Test circular dependency behavior — see [Circular dependencies](user-guide/circular-dependencies.md)

## Best Practices

- **Keep specs simple**: Break complex wiring into smaller, focused specs
- **Use placeholders**: Express dependencies explicitly with `{name}` syntax
- **Validate early**: Access all wired objects in tests to catch configuration errors
- **Document dependencies**: Comment complex dependency chains in your specs
- **Consider thread safety**: Enable `thread_safe=True` only when needed (has overhead)
- **Compile for production**: Use `WiringCompiler` to generate optimized code

## Next Steps

Start with [Basic Usage](basic-usage.md) to learn the fundamentals, then explore the other guides based on your specific needs.
