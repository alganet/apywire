# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

"""Exception classes for apywire.

This module contains all exception types used throughout the apywire
library, including exceptions for wiring errors and thread-safety
internal exceptions.
"""


class WiringError(AttributeError):
    """Raised when the wiring system cannot instantiate an attribute.

    This wraps the underlying exception to provide context on which
    attribute failed to instantiate, while preserving the original
    exception as the cause.
    """


class UnknownPlaceholderError(WiringError):
    """Raised by `_resolve_runtime` when a placeholder name is not
    found in either constants (`_values`) or parsed spec entries
    (`_parsed`).
    """


class CircularWiringError(WiringError):
    """Raised when a circular wiring dependency is detected.

    This class is a `WiringError` subtype for simpler programmatic
    handling of wiring-specific failures.

    Utility: construct a helpful message from a dependency mapping and
    unprocessed nodes when a topological sort fails.
    """

    @classmethod
    def from_unprocessed(
        cls, dependencies: dict[str, set[str]], unprocessed: list[str]
    ) -> "CircularWiringError":
        """Create a CircularWiringError that includes a cycle when possible.

        Args:
            dependencies: Full mapping of node -> dependencies
            unprocessed: List of nodes left unprocessed by topological sort

        Returns:
            CircularWiringError instance with a helpful message.
        """
        all_nodes = set(dependencies.keys())

        # Use DFS limited to unprocessed nodes to find any back-edge cycle path
        visited: set[str] = set()
        stack: list[str] = []
        on_stack: set[str] = set()

        def dfs(node: str) -> list[str] | None:
            visited.add(node)
            stack.append(node)
            on_stack.add(node)
            for nbr in dependencies.get(node, set()):
                if nbr not in all_nodes:
                    continue
                if nbr not in visited:
                    res = dfs(nbr)
                    if res:
                        return res
                elif nbr in on_stack:
                    try:
                        idx = stack.index(nbr)
                    except ValueError:
                        idx = 0
                    return stack[idx:] + [nbr]
            stack.pop()
            on_stack.remove(node)
            return None

        for start in unprocessed:
            if start not in visited:
                cyc = dfs(start)
                if cyc:
                    return cls(
                        f"Circular dependency detected: {
                            ', '.join(unprocessed)
                        }; "
                        f"cycle: {' -> '.join(cyc)}"
                    )

        return cls(f"Circular dependency detected: {', '.join(unprocessed)}")


class LockUnavailableError(RuntimeError):
    """Exception raised when a per-attribute lock cannot be acquired in
    optimistic (non-blocking) mode and the code must fall back to a global
    lock.

    This exception is used internally by the thread-safety system but is also
    referenced in compiled code, so it is part of the public API.
    """


class FormatError(ValueError):
    """Raised when parsing or serializing a spec in a specific format fails.

    This wraps the underlying parsing exception to provide context about
    the format being used and a user-friendly error message.
    """

    def __init__(self, fmt: str, message: str) -> None:
        self.format = fmt
        super().__init__(f"{fmt.upper()} format error: {message}")
