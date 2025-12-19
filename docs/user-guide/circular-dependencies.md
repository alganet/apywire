<!--
SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>

SPDX-License-Identifier: ISC
-->

# Circular dependencies

Circular dependencies occur when two or more wired entries reference each other (directly or transitively), producing a resolution loop that cannot be satisfied.

This guide explains how apywire detects cycles, what exception is raised, examples, and practical ways to avoid them.

---

## Overview

When a spec contains placeholders that form a cycle, wiring cannot determine a deterministic instantiation order. apywire treats cycles as errors and reports them so you can fix your design or introduce a controlled indirection.

## How apywire detects cycles

- During parsing and initialization, apywire builds a dependency graph that maps exposed wiring names to the placeholders they reference.
- The container attempts a topological sort (Kahn's algorithm) to determine an instantiation order. If the sort cannot process all nodes, the remaining nodes are part of a cycle.
- The `Generator` utility also tracks visited entries and stops recursion silently when it detects recursion.

## Exception raised

When a cycle is detected apywire raises `CircularWiringError`. The exception message lists the involved entries and, when possible, includes a readable cycle chain showing the resolution order.

Example (wired objects):

```python
from apywire import Wiring, CircularWiringError

spec = {
    "MyClass a": {"dep": "{b}"},
    "MyClass b": {"dep": "{a}"},
}

try:
    Wiring(spec)
except CircularWiringError as e:
    print(e)
    # Example output: Circular dependency detected: a, b; cycle: a -> b -> a
```

Example (constants):

```python
from apywire import Wiring, CircularWiringError

spec = {
    "a": "{b}",
    "b": "{a}",
}

try:
    Wiring(spec)
except CircularWiringError as e:
    print(e)
    # Example output (actual): Circular dependency detected: a, b; cycle: a -> b -> a
```

## Examples

Simple two-node cycle (wired objects):

```python
from apywire import Wiring, CircularWiringError

spec = {
    "MyClass a": {"dependency": "{b}"},
    "MyClass b": {"dependency": "{a}"},  # Circular!
}

try:
    wired = Wiring(spec)
except CircularWiringError as e:
    print(e)
```

Cycle in constant placeholders:

```python
from apywire import Wiring, CircularWiringError

spec = {
    "a": "{b}",
    "b": "{a}",
}

with pytest.raises(CircularWiringError):
    Wiring(spec)
```

For async accessors, cycles are detected during Wiring() initialization just like for synchronous usage, and a `CircularWiringError` is raised before any async accessors are created.

## How to avoid circular dependencies

- Split responsibilities into smaller, decoupled components so they don't require mutual placeholders.
- Use a factory or late-bound accessor instead of a placeholder for one side of the relationship.
- Inject interfaces or configuration rather than concrete implementations when suitable.
- Use compilation or explicit initialization ordering when you need concrete control over instantiation.

## Thread-safety and cross-thread detection

Cycle detection for placeholders is performed during spec parsing/initialization using a topological sort, so cycles are detected early and reported via `CircularWiringError`. When `thread_safe=True`, apywire additionally uses per-attribute locks to serialize instantiation; thread-local storage is used to keep lock-related per-thread state and avoid cross-thread interference (see `threads.py` for details).

## Troubleshooting and tips

- Reproduce the cycle with a small spec and a focused test.
- Inspect the error message chain to identify the involved entries.
- If a cycle is intentional, convert one dependency to a factory or resolver to avoid placeholder-based cycles.

---

See also: `Wiring` (../user-guide/basic-usage.md) — if you have questions about a specific scenario, add a short reproducer test and we can help iterate on recommendations.
