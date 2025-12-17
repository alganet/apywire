# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC


"""Base wiring functionality.

This module defines the core type system and base class for wiring
containers:

- _SpecValue: Raw values from user-provided spec (may include "{name}"
              placeholders)
- _ResolvedValue: After parsing, placeholders become _WiredRef markers
- _RuntimeValue: Concrete instantiated objects at runtime
"""

from __future__ import annotations

import re
from collections import deque
from types import EllipsisType
from typing import NamedTuple, TypeAlias, cast

from apywire.constants import (
    PLACEHOLDER_END,
    PLACEHOLDER_REGEX,
    PLACEHOLDER_START,
    SPEC_KEY_DELIMITER,
    SYNTHETIC_CONST,
)
from apywire.exceptions import CircularWiringError, UnknownPlaceholderError

_ConstantValue: TypeAlias = (
    str | bytes | bool | int | float | complex | EllipsisType | None
)


class _WiredRef:
    """Marker for a value that references another wired attribute.

    Resolved lazily at instantiation.
    """

    __slots__ = ("name",)

    def __init__(self, name: str) -> None:
        self.name = name


# User-provided spec values: primitives, containers, or placeholders
_SpecValue: TypeAlias = (
    _ConstantValue
    | str
    | list["_SpecValue"]
    | tuple["_SpecValue", ...]
    | dict[str | int, "_SpecValue"]
)

# After parsing: placeholder strings "{name}" become _WiredRef markers
_ResolvedValue: TypeAlias = (
    _ConstantValue
    | _WiredRef
    | list["_ResolvedValue"]
    | tuple["_ResolvedValue", ...]
    | dict[str | int, "_ResolvedValue"]
)

# Runtime values are the concrete types available at runtime —
# constants, objects and nested containers.
_RuntimeValue: TypeAlias = (
    object
    | _ConstantValue
    | list["_RuntimeValue"]
    | tuple["_RuntimeValue", ...]
    | dict[str | int, "_RuntimeValue"]
)

_SpecMapping: TypeAlias = dict[str | int, _SpecValue] | list["_SpecValue"]
# Public alias to annotate an individual spec mapping entry.
# Example: `def build(spec: apywire.SpecEntry) -> apywire.Spec: ...`
SpecEntry: TypeAlias = dict[str | int, _SpecValue]
_ResolvedSpecMapping: TypeAlias = (
    dict[str | int, _ResolvedValue] | list["_ResolvedValue"]
)
Spec: TypeAlias = dict[str, _SpecMapping | _ConstantValue]


class _ParsedEntry(NamedTuple):
    """A parsed wiring entry ready for instantiation."""

    module_name: str
    class_name: str
    factory_method: str | None
    data: _ResolvedSpecMapping | str | _WiredRef


class _UnresolvedParsedEntry(NamedTuple):
    """An intermediate parsed entry before placeholder resolution."""

    module_name: str
    class_name: str
    name: str
    factory_method: str | None
    data: _SpecMapping


class WiringBase:
    """Base class for wiring containers."""

    _parsed: dict[str, _ParsedEntry]
    _values: dict[str, _RuntimeValue]

    def __init__(
        self,
        spec: Spec,
        *,
        thread_safe: bool = False,
        max_lock_attempts: int = 10,
        lock_retry_sleep: float = 0.01,
    ) -> None:
        """Initialize a Wiring container.

        Args:
            spec: The wiring spec mapping.
            thread_safe: Enable thread-safe instantiation (default: False).
            max_lock_attempts: Max retries in global lock mode
                               (only when thread_safe=True).
            lock_retry_sleep: Sleep time in seconds between lock retries
                              (only when thread_safe=True).
        """
        self._thread_safe = thread_safe
        self._max_lock_attempts = max_lock_attempts
        self._lock_retry_sleep = lock_retry_sleep

        parsed: list[_UnresolvedParsedEntry] = []
        consts: dict[str, _SpecMapping | _ConstantValue] = {}

        # First pass: classify entries into wired classes or constants
        for key, value in spec.items():
            entry = self._parse_spec_entry(key, value)
            if entry is not None:
                parsed.append(entry)
            else:
                # It's a constant
                consts[key] = value

        # Parse wired objects first
        self._parsed: dict[str, _ParsedEntry] = {
            entry.name: _ParsedEntry(
                entry.module_name,
                entry.class_name,
                entry.factory_method,
                cast(_ResolvedSpecMapping, self._resolve(entry.data)),
            )
            for entry in parsed
        }

        # Classify constants by placeholder type
        raw_consts: dict[str, _SpecMapping | _ConstantValue] = {}
        const_with_refs: dict[
            str, tuple[_SpecMapping | _ConstantValue, set[str]]
        ] = {}

        for key, value in consts.items():
            placeholder_names = self._find_placeholder_names(value)
            if not placeholder_names:
                # No placeholders - store immediately
                raw_consts[key] = value
            else:
                # Has placeholders - classify later
                const_with_refs[key] = (value, placeholder_names)

        # Promote constants to accessors if they reference wired objects:
        # Transitive: mark direct refs, then propagate to dependents
        const_deps_graph: dict[str, set[str]] = {
            key: placeholder_names
            for key, (value, placeholder_names) in const_with_refs.items()
        }
        # Initially, mark constants that directly reference a wired object
        to_promote = set()
        for key, (value, placeholder_names) in const_with_refs.items():
            if any(name in self._parsed for name in placeholder_names):
                to_promote.add(key)
        # Propagate promotion transitively
        changed = True
        while changed:
            changed = False
            for key, deps in const_deps_graph.items():
                if key in to_promote:
                    continue
                if any(dep in to_promote for dep in deps):
                    to_promote.add(key)
                    changed = True
        # Now, split into promoted and pure-constant refs
        const_with_const_refs: dict[str, _SpecMapping | _ConstantValue] = {}
        const_with_wired_refs: dict[str, _SpecMapping | _ConstantValue] = {}
        for key, (value, placeholder_names) in const_with_refs.items():
            if key in to_promote:
                const_with_wired_refs[key] = value
            else:
                const_with_const_refs[key] = value

        # Topologically sort and expand constant-only refs
        if const_with_const_refs:
            const_deps = {
                k: self._find_placeholder_names(v)
                for k, v in const_with_const_refs.items()
            }
            sorted_const_keys = self._topological_sort(const_deps)
        else:
            sorted_const_keys = []

        # Resolve constants in dependency order
        resolved_consts: dict[str, _RuntimeValue] = dict(raw_consts)
        for key in sorted_const_keys:
            resolved = self._resolve_constant(
                const_with_const_refs[key], resolved_consts
            )
            resolved_consts[key] = resolved

        self._values: dict[str, _RuntimeValue] = resolved_consts

        # Create synthetic parsed entries for auto-promoted constants
        for key, value in const_with_wired_refs.items():
            # Create a synthetic entry that will format the string at runtime
            self._parsed[key] = _ParsedEntry(
                SYNTHETIC_CONST,  # Synthetic module marker
                "str",  # Will use string formatting
                None,  # No factory method
                cast(str | _WiredRef, self._resolve(value)),
            )
        if not self._thread_safe:
            # Non-thread-safe mode: use simple list for resolving stack
            self._resolving_stack: list[str] = []

    def _parse_spec_entry(
        self, key: str, value: _SpecMapping | _ConstantValue
    ) -> _UnresolvedParsedEntry | None:
        """Parse a spec entry. Returns None for constants."""
        if SPEC_KEY_DELIMITER not in key:
            return None  # It's a constant

        # class wiring: "module.Class name" or
        # "module.Class name.factoryMethod"
        type_str, name_part = key.rsplit(SPEC_KEY_DELIMITER, 1)
        parts = type_str.split(".")
        module_name = ".".join(parts[:-1])
        class_name = parts[-1]

        # Check if name_part contains a factory method
        # e.g., "myInstance.from_date" -> name="myInstance",
        # factory_method="from_date"
        if "." in name_part:
            name, factory_method = name_part.split(".", 1)
            if "." in factory_method:
                raise ValueError(
                    f"invalid spec key '{key}': nested factory methods "
                    f"are not supported."
                )
        else:
            name = name_part
            factory_method = None

        if not module_name:
            raise ValueError(
                f"invalid spec key '{key}': missing module qualification"
            )

        return _UnresolvedParsedEntry(
            module_name,
            class_name,
            name,
            factory_method,
            cast(_SpecMapping, value),
        )

    def _is_placeholder(self, s: str) -> bool:
        """Check if a string is a placeholder reference like '{name}'."""
        return s.startswith(PLACEHOLDER_START) and s.endswith(PLACEHOLDER_END)

    def _extract_placeholder_name(self, s: str) -> str:
        """Extract the name from a placeholder string like '{name}'.

        Args:
            s: Placeholder string (must be validated with
               _is_placeholder first)

        Returns:
            The placeholder name without braces
        """
        return s.removeprefix(PLACEHOLDER_START).removesuffix(PLACEHOLDER_END)

    def _resolve(self, obj: _SpecValue) -> _ResolvedValue:
        """Resolve placeholders into `_WiredRef` markers for runtime.

        Replaces strings of the form "{name}" with a `_WiredRef(name)`
        for later resolution.
        """
        if isinstance(obj, str):
            if self._is_placeholder(obj):
                ref_name = self._extract_placeholder_name(obj)
                return _WiredRef(ref_name)
            return obj
        elif isinstance(obj, dict):
            return {k: self._resolve(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._resolve(v) for v in obj]
        elif isinstance(obj, tuple):
            return tuple(self._resolve(v) for v in obj)
        return obj

    def _interpolate_placeholders(
        self,
        template: str,
        lookup: dict[str, _RuntimeValue],
        context: str = "",
    ) -> str:
        """Replace placeholders in a string template with values.

        Args:
            template: String containing placeholders like "{name}"
            lookup: Dictionary mapping placeholder names to values
            context: Optional context for error messages

        Returns:
            String with all placeholders replaced by their string values

        Raises:
            UnknownPlaceholderError: If placeholder name not in lookup
        """

        def replace_placeholder(match: re.Match[str]) -> str:
            ref_name = match.group(1)
            if ref_name not in lookup:
                ctx_msg = f" in {context}" if context else ""
                raise UnknownPlaceholderError(
                    f"Unknown placeholder '{ref_name}'{ctx_msg}"
                )
            ref_value = lookup[ref_name]
            return (
                str(ref_value) if not isinstance(ref_value, str) else ref_value
            )

        return PLACEHOLDER_REGEX.sub(replace_placeholder, template)

    def _find_placeholder_names(self, obj: _SpecValue) -> set[str]:
        """Find all placeholder names referenced in a value.

        Args:
            obj: Value to search for placeholders

        Returns:
            Set of placeholder names found
        """
        names: set[str] = set()
        if isinstance(obj, str):
            # Find all placeholders in the string (embedded or not)
            matches: list[str] = PLACEHOLDER_REGEX.findall(obj)
            names.update(matches)
        elif isinstance(obj, dict):
            for v in obj.values():
                names.update(self._find_placeholder_names(v))
        elif isinstance(obj, (list, tuple)):
            for v in obj:
                names.update(self._find_placeholder_names(v))
        return names

    def _topological_sort(
        self, dependencies: dict[str, set[str]]
    ) -> list[str]:
        """Topologically sort items by dependency order using Kahn's algorithm.

        Args:
            dependencies: Mapping of item names to their dependencies

        Returns:
            List of items in dependency order (dependencies first)

        Raises:
            CircularWiringError: If circular dependencies detected
        """
        # Calculate in-degree (number of dependencies) for each node
        # Pre-convert to set for efficient intersection
        all_nodes = set(dependencies.keys())
        in_degree: dict[str, int] = {}
        for node, deps in dependencies.items():
            # Filter to only dependencies within this set
            internal_deps = deps & all_nodes
            in_degree[node] = len(internal_deps)

        # Start with nodes that have no dependencies (within this set)
        queue: deque[str] = deque(
            [node for node, degree in in_degree.items() if degree == 0]
        )
        result: list[str] = []

        while queue:
            node = queue.popleft()
            result.append(node)

            # Find nodes that depend on this node (within this set)
            for other_node, deps in dependencies.items():
                if node in deps:
                    in_degree[other_node] -= 1
                    if in_degree[other_node] == 0:
                        queue.append(other_node)

        # If we couldn't process all nodes, there's a cycle
        if len(result) != len(dependencies):
            # Find nodes in cycle for error message
            unprocessed = [n for n in dependencies if n not in result]
            raise CircularWiringError(
                f"Circular dependency detected in constants: "
                f"{', '.join(unprocessed)}"
            )

        return result

    def _resolve_constant(
        self, value: _SpecValue, resolved: dict[str, _RuntimeValue]
    ) -> _RuntimeValue:
        """Resolve a constant value, expanding ONLY constant placeholders.

        Constant placeholders are expanded immediately. Wired object
        placeholders should not appear here as those constants are
        auto-promoted to accessors.

        Args:
            value: Constant value to resolve
            resolved: Already-resolved constants available for reference

        Returns:
            Fully resolved constant value

        Raises:
            UnknownPlaceholderError: If placeholder references unknown constant
        """
        if isinstance(value, str):
            # Check if the entire string is a single placeholder
            if self._is_placeholder(value):
                ref_name = self._extract_placeholder_name(value)
                if ref_name not in resolved:
                    raise UnknownPlaceholderError(
                        f"Unknown constant placeholder '{ref_name}'"
                    )
                # Return the resolved value directly
                ref_value = resolved[ref_name]
                return (
                    str(ref_value)
                    if not isinstance(ref_value, str)
                    else ref_value
                )

            # Handle embedded placeholders via string interpolation
            return self._interpolate_placeholders(value, resolved, "constant")
        elif isinstance(value, dict):
            return {
                k: self._resolve_constant(v, resolved)
                for k, v in value.items()
            }
        elif isinstance(value, list):
            return [self._resolve_constant(v, resolved) for v in value]
        elif isinstance(value, tuple):
            return tuple(self._resolve_constant(v, resolved) for v in value)
        return value
