# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC


"""Core wiring functionality."""

from __future__ import annotations

import asyncio
import importlib
import re
from operator import itemgetter
from typing import Awaitable, Callable, Protocol, cast, final

from apywire.constants import SYNTHETIC_CONST
from apywire.exceptions import (
    CircularWiringError,
    UnknownPlaceholderError,
    WiringError,
)
from apywire.threads import ThreadSafeMixin
from apywire.wiring import (
    Spec,
    SpecEntry,
    WiringBase,
    _ResolvedValue,
    _RuntimeValue,
    _WiredRef,
)

__all__ = [
    "WiringRuntime",
    "Accessor",
    "AioAccessor",
    "Spec",
    "SpecEntry",
]


class _Constructor(Protocol):
    """Protocol for callable constructors.

    This protocol represents any callable that can be used as a class
    constructor, accepting arbitrary positional and keyword arguments
    and returning an instance of the constructed class.
    """

    def __call__(self, *args: object, **kwargs: object) -> object: ...


class WiringRuntime(WiringBase, ThreadSafeMixin):
    """Runtime container for wired objects.

    This class handles the runtime resolution and instantiation of wired
    objects. It does NOT support compilation; use `WiringCompiler` for that.
    """

    def __init__(
        self,
        spec: Spec,
        *,
        thread_safe: bool = False,
        max_lock_attempts: int = 10,
        lock_retry_sleep: float = 0.01,
    ) -> None:
        """Initialize a WiringRuntime container.

        Args:
            spec: The wiring spec mapping.
            thread_safe: Enable thread-safe instantiation (default: False).
            max_lock_attempts: Max retries in global lock mode
                               (only when thread_safe=True).
            lock_retry_sleep: Sleep time in seconds between lock retries
                               (only when thread_safe=True).
        """
        super().__init__(
            spec,
            thread_safe=thread_safe,
            max_lock_attempts=max_lock_attempts,
            lock_retry_sleep=lock_retry_sleep,
        )
        if self._thread_safe:
            self._init_thread_safety(max_lock_attempts, lock_retry_sleep)

    def _init_thread_safety(
        self,
        max_lock_attempts: int = 10,
        lock_retry_sleep: float = 0.01,
    ) -> None:
        """Initialize thread safety mixin."""
        ThreadSafeMixin._init_thread_safety(
            self, max_lock_attempts, lock_retry_sleep
        )

    def _get_resolving_stack(self) -> list[str]:
        """Return the resolving stack for the current context."""
        if self._thread_safe:
            return ThreadSafeMixin._get_resolving_stack(self)
        return self._resolving_stack

    def __getattr__(self, name: str) -> Accessor:
        """Return a callable accessor for the named wired object."""
        # If the name is in our parsed spec or constants, return an accessor.
        if name in self._parsed or name in self._values:
            return Accessor(self, name)
        raise AttributeError(
            f"'{type(self).__name__}' object has no attribute '{name}'"
        )

    @property
    def aio(self) -> "AioAccessor":
        """Return a wrapper object providing async accessors.

        Use `await wired.aio.name()` to obtain the instantiated value
        asynchronously. We use `aio` to avoid the reserved keyword
        `async` (so `wired.async` would be invalid syntax).
        """
        if not hasattr(self, "_aio_accessor"):
            self._aio_accessor = AioAccessor(self)
        return self._aio_accessor

    def _instantiate_attr(
        self,
        name: str,
        maker: Callable[[], object],
    ) -> object:
        """Instantiate an attribute using the configured strategy.

        If thread_safe is True, uses the ThreadSafeMixin implementation
        which handles optimistic locking and global fallback.
        If thread_safe is False, uses a simple direct instantiation.
        """
        if self._thread_safe:
            # Use the mixin's implementation which handles locking
            return ThreadSafeMixin._instantiate_attr(self, name, maker)

        # Non-thread-safe path: simple check and set
        if name in self._values:
            return self._values[name]

        # No locking needed
        val = maker()
        self._values[name] = val
        return val

    def _separate_args_kwargs(
        self, data: dict[str | int, object]
    ) -> tuple[list[object], dict[str, object]]:
        """Separate positional args (int keys) from keyword args (str keys).

        Args:
            data: Dictionary with mixed int and str keys

        Returns:
            Tuple of (positional_args, keyword_args)
        """
        # Iterate once over data.items() to separate args and kwargs
        args_list = []
        kwargs_dict = {}
        for k, v in data.items():
            if isinstance(k, int):
                args_list.append((k, v))
            else:
                kwargs_dict[k] = v

        # Sort positional args by index and extract values
        args_list.sort(key=itemgetter(0))
        pos_args = [v for _, v in args_list]

        return (pos_args, kwargs_dict)

    def _instantiate_impl(self, name: str) -> _RuntimeValue:
        """Internal implementation of instantiation logic.

        This method is called by _instantiate_attr (via the maker lambda)
        to actually create the object if it's not cached.

        Positional Arguments Support:
        When the spec contains integer keys (e.g., {0: value, 1: value}),
        these are treated as positional arguments and are separated from
        keyword arguments before calling the constructor.

        Factory Method Support:
        When a factory method is specified in the spec key (e.g.,
        "module.Class instance.from_date"), the factory method is called
        instead of the class constructor.
        """
        # Check for circular dependencies
        stack = self._get_resolving_stack()
        if name in stack:
            raise CircularWiringError(
                f"Circular wiring dependency detected: "
                f"{' -> '.join(stack)} -> {name}"
            )

        stack.append(name)
        try:
            if name in self._values:
                return self._values[name]

            if name not in self._parsed:
                # Should have been caught by __getattr__ or _resolve_runtime,
                # but just in case.
                raise UnknownPlaceholderError(
                    f"Unknown placeholder '{name}' referenced."
                )

            entry = self._parsed[name]

            # Check for synthetic auto-promoted constant
            if (
                entry.module_name == SYNTHETIC_CONST
                and entry.class_name == "str"
            ):
                # This is an auto-promoted constant with string interpolation
                value = self._format_string_constant(entry.data, context=name)
                self._values[name] = value
                return value

            module = importlib.import_module(entry.module_name)
            cls = cast(_Constructor, getattr(module, entry.class_name))

            # If a factory method is specified, get it from the class
            if entry.factory_method:
                constructor = cast(
                    _Constructor, getattr(cls, entry.factory_method)
                )
            else:
                constructor = cls

            # Resolve arguments
            kwargs = self._resolve_runtime(entry.data, context=name)

            try:
                if isinstance(kwargs, dict):
                    # Separate positional args (int keys) from keyword args
                    # (str keys)
                    pos_args, kwargs_dict = self._separate_args_kwargs(kwargs)
                    instance = constructor(*pos_args, **kwargs_dict)
                elif isinstance(kwargs, list):
                    # All positional arguments
                    instance = constructor(*kwargs)
                else:
                    instance = constructor(kwargs)
            except Exception as e:
                raise WiringError(
                    f"failed to instantiate '{name}': {e}"
                ) from e

            return instance
        finally:
            stack.pop()

    def _resolve_runtime(
        self,
        o: _ResolvedValue,
        context: str | None = None,
    ) -> _RuntimeValue:
        """Recursively resolve values at runtime.

        Converts `_WiredRef` placeholders into actual objects by calling
        their accessors.
        """
        if isinstance(o, _WiredRef):
            # Ensure placeholder was defined in spec
            if o.name not in self._values and o.name not in self._parsed:
                ctx = f" while instantiating '{context}'" if context else ""
                raise UnknownPlaceholderError(
                    f"Unknown placeholder '{o.name}' referenced{ctx}."
                )
            # Membership check ensures `o.name` is known; if getattr raises
            # AttributeError it's from instance creation — let it propagate.
            # Call the accessor `self.name()` to get the runtime value.
            return cast(object, getattr(self, o.name)())

        elif isinstance(o, dict):
            return {k: self._resolve_runtime(v, context) for k, v in o.items()}
        elif isinstance(o, list):
            return [self._resolve_runtime(v, context) for v in o]
        elif isinstance(o, tuple):
            return tuple(self._resolve_runtime(v, context) for v in o)
        return o

    def _format_string_constant(
        self, template: _ResolvedValue, context: str
    ) -> str:
        """Format a string constant with wired object interpolation.

        Converts template like "Server {host} at {now}" by:
        1. Finding all placeholders in the string
        2. Resolving each to its wired object or constant
        3. Converting to string via str()
        4. Performing string interpolation

        Args:
            template: Template string with placeholders
            context: Name of the constant being formatted (for error messages)

        Returns:
            Fully formatted string with all placeholders resolved

        Raises:
            WiringError: If template is not a string
            UnknownPlaceholderError: If placeholder references unknown object
        """
        # Template should be a string
        if not isinstance(template, str):
            raise WiringError(
                f"Auto-promoted constant '{context}' template is not a string"
            )

        # Build lookup dict that resolves wired objects on access
        # We can't use _interpolate_placeholders directly because we need
        # to call getattr() for wired objects, not just lookup in a dict
        def replace_placeholder(match: re.Match[str]) -> str:
            ref_name = match.group(1)

            # Check if the referenced name exists
            if ref_name not in self._values and ref_name not in self._parsed:
                raise UnknownPlaceholderError(
                    f"Unknown placeholder '{ref_name}' "
                    f"in auto-promoted constant '{context}'"
                )

            # Get the value (instantiate if needed via accessor)
            value = cast(object, getattr(self, ref_name)())

            # Convert to string
            return str(value)

        return re.sub(self._placeholder_pattern, replace_placeholder, template)


@final
class Accessor:
    """A callable object that retrieves a wired value."""

    def __init__(self, wiring: WiringRuntime, name: str) -> None:
        self._wiring = wiring
        self._name = name

    def __call__(self) -> object:
        """Return the wired object, instantiating it if necessary."""
        # Fast path: EAFP pattern for cache lookup
        # Try to get cached value directly (faster than check + get)
        try:
            return self._wiring._values[self._name]
        except KeyError:
            pass

        # Not cached, so we need to instantiate it.
        # We use _instantiate_attr which handles thread safety if enabled.
        return self._wiring._instantiate_attr(
            self._name, lambda: self._wiring._instantiate_impl(self._name)
        )


@final
class AioAccessor:
    """Helper for accessing wired objects asynchronously."""

    def __init__(self, wiring: WiringRuntime) -> None:
        self._wiring = wiring

    def __getattr__(self, name: str) -> Callable[[], Awaitable[object]]:
        """Return an async callable for the named wired object."""
        # Check if valid name
        if (
            name not in self._wiring._parsed
            and name not in self._wiring._values
        ):
            raise AttributeError(
                f"'{type(self._wiring).__name__}' object has no attribute "
                f"'{name}'"
            )

        async def _get() -> object:
            # EAFP: Try cached value first
            try:
                return self._wiring._values[name]
            except KeyError:
                pass

            # If not cached, run instantiation in executor to avoid blocking
            # the event loop.
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                None,
                lambda: self._wiring._instantiate_attr(
                    name, lambda: self._wiring._instantiate_impl(name)
                ),
            )

        return _get
