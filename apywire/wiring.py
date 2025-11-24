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

from types import EllipsisType
from typing import TypeAlias, cast

from apywire.constants import (
    PLACEHOLDER_END,
    PLACEHOLDER_START,
    SPEC_KEY_DELIMITER,
)
from apywire.threads import ThreadLocalState

_ConstantValue: TypeAlias = (
    str | bytes | bool | int | float | complex | EllipsisType | None
)


# Marker class for a placeholder reference. Declared before the
# type aliases so `ResolvedValue` can reference it directly.
class _WiredRef:
    """Marker for a value that references another wired attribute.

    Resolved lazily at instantiation.
    """

    __slots__ = ("name",)

    def __init__(self, name: str) -> None:
        self.name = name


# Spec value types come from the user-provided `Spec` input. They are
# primitives or nested containers and may include placeholder strings
# like "{otherName}".
_SpecValue: TypeAlias = (
    _ConstantValue
    | str
    | list["_SpecValue"]
    | tuple["_SpecValue", ...]
    | dict[str | int, "_SpecValue"]
)

# Resolved values are produced after parsing placeholders; strings of
# the form "{name}" become `_WiredRef` markers and are resolved at
# instantiation.
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

# Type aliases for parsed spec entries
_ParsedEntry: TypeAlias = tuple[
    str, str, str | None, _ResolvedSpecMapping
]  # (module, class, factory_method, data)
_UnresolvedParsedEntry: TypeAlias = tuple[
    str, str, str, str | None, _SpecMapping
]  # (module, class, name, factory_method, data)


class _ThreadLocalState(ThreadLocalState):
    """Thread-local state for wiring resolution.

    Inherits from ThreadLocalState to get properly typed attributes.
    """


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
        consts: dict[str, _ConstantValue] = {}

        # First pass: classify entries into wired classes or constants
        for key, value in spec.items():
            entry = self._parse_spec_entry(key, value)
            if entry is not None:
                parsed.append(entry)
            else:
                # It's a constant
                consts[key] = cast(_ConstantValue, value)

        # Merge constants into the initial runtime cache
        self._values: dict[str, _RuntimeValue] = dict(consts)

        # Resolve placeholders like "{name}" using _resolve.

        self._parsed: dict[str, _ParsedEntry] = {
            name: (
                module_name,
                class_name,
                factory_method,
                cast(_ResolvedSpecMapping, self._resolve(value)),
            )
            for module_name, class_name, name, factory_method, value in parsed
        }
        # Instances will be lazily instantiated and stored in self._values
        if self._thread_safe:
            # Thread-safe mode: use mixin helpers for lock state.
            # Note: Derived classes must implement _init_thread_safety
            # if they support thread safety (like WiringRuntime).
            if hasattr(self, "_init_thread_safety"):
                self._init_thread_safety(max_lock_attempts, lock_retry_sleep)
        else:
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

        return (
            module_name,
            class_name,
            name,
            factory_method,
            cast(_SpecMapping, value),
        )

    def _is_placeholder(self, s: str) -> bool:
        """Check if a string is a placeholder reference like '{name}'."""
        return s.startswith(PLACEHOLDER_START) and s.endswith(PLACEHOLDER_END)

    def _resolve(self, obj: _SpecValue) -> _ResolvedValue:
        """Resolve placeholders into `_WiredRef` markers for runtime.

        Replaces strings of the form "{name}" with a `_WiredRef(name)`
        for later resolution.
        """
        if isinstance(obj, str):
            if self._is_placeholder(obj):
                ref_name = obj[len(PLACEHOLDER_START) : -len(PLACEHOLDER_END)]
                return _WiredRef(ref_name)
            return obj
        if isinstance(obj, dict):
            return {k: self._resolve(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._resolve(v) for v in obj]
        if isinstance(obj, tuple):
            return tuple(self._resolve(v) for v in obj)
        return obj
