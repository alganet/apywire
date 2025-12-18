# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC


"""Core wiring functionality."""

from __future__ import annotations

import asyncio
import importlib
import re
import threading
from functools import cached_property
from operator import itemgetter
from typing import Awaitable, Callable, Optional, Protocol, cast, final

from apywire.constants import PLACEHOLDER_REGEX, SYNTHETIC_CONST
from apywire.exceptions import (
    CircularWiringError,
    PartialConstructionError,
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
        allow_partial: bool = False,
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
            allow_partial=allow_partial,
        )
        # Retain allow_partial attribute for clarity
        self.allow_partial = allow_partial
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

    def _skeletonize_type(self, cls: _Constructor) -> object:
        """Allocate a skeleton instance for the given class-like constructor.

        The skeleton is created via cls.__new__(cls) and marked as partial.
        We attach a threading.Event to allow other threads to wait for
        finalization.
        """
        try:
            # The call to __new__ can confuse the type checker; narrow via cast
            skeleton: object = cast(
                object, cls.__new__(cls)  # type: ignore[arg-type]
            )
        except Exception as e:
            raise PartialConstructionError(
                f"failed to allocate skeleton for {cls}: {e}"
            ) from e
        # Mark skeleton as partial and attach sync primitives
        try:
            setattr(skeleton, "_apywire_partial", True)
            setattr(skeleton, "_apywire_event", threading.Event())
            setattr(skeleton, "_apywire_failure", None)
        except Exception:
            # If we cannot attach markers, treat as not skeletonizable
            raise PartialConstructionError(
                f"type {cls} cannot be skeletonized"
            )
        return skeleton

    def _finalize_skeleton(
        self, skeleton: object, exc: Exception | None = None
    ) -> None:  # pragma: no cover - defensive notification only
        """Finalize or fail a previously allocated skeleton.

        If exc is None, the skeleton is marked finalized and waiters are
        notified. Otherwise, the failure is recorded and waiters are
        notified before cleanup is performed by the caller.
        """
        if exc is not None:
            try:
                setattr(skeleton, "_apywire_failure", exc)
            except Exception:  # pragma: no cover - defensive
                pass
        try:
            setattr(skeleton, "_apywire_partial", False)
            event = cast(
                Optional[threading.Event],
                getattr(skeleton, "_apywire_event", None),
            )
            if event is not None:
                try:
                    event.set()
                except Exception:  # pragma: no cover - defensive
                    pass
        except Exception:  # pragma: no cover - defensive
            # Best-effort: ignore finalization errors
            pass

    def _cleanup_skeleton(
        self, name: str, skeleton: object, exc: Exception | None = None
    ) -> None:
        """Finalize skeleton, record failure and remove it from cache.

        This is a convenience helper to centralize the cleanup policy used
        when partial construction fails or a factory violates expectations.
        """
        try:
            self._finalize_skeleton(skeleton, exc)
        finally:
            if name in self._values and self._values[name] is skeleton:
                del self._values[name]

    def __getattr__(self, name: str) -> Accessor:
        """Return a callable accessor for the named wired object."""
        # Return accessor for known names
        if name in self._parsed or name in self._values:
            return Accessor(self, name)
        raise AttributeError(
            f"'{type(self).__name__}' object has no attribute '{name}'"
        )

    @cached_property
    def aio(self) -> "AioAccessor":
        """Return a wrapper object providing async accessors.

        Use `await wired.aio.name()` to obtain the instantiated value
        asynchronously. We use `aio` to avoid the reserved keyword
        `async` (so `wired.async` would be invalid syntax).
        """
        return AioAccessor(self)

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
            # Opt-in partial construction: allocate a skeleton placeholder
            if not self.allow_partial:
                msg = (
                    "Circular wiring dependency detected: "
                    + " -> ".join(stack)
                    + " -> "
                    + name
                )
                raise CircularWiringError(msg)

            # Create and cache a skeleton placeholder for the declared type
            if name in self._parsed:
                entry = self._parsed[name]
                # Only class-like types can be skeletonized
                if (
                    entry.module_name == SYNTHETIC_CONST
                    and entry.class_name == "str"
                ):
                    raise CircularWiringError(
                        "Circular wiring dependency detected while resolving "
                        + repr(name)
                    )
                module = importlib.import_module(entry.module_name)
                cls = cast(_Constructor, getattr(module, entry.class_name))
                skeleton = self._skeletonize_type(cls)
                # Insert into cache. Use _set_cache if provided for
                # thread-safe paths.
                if hasattr(self, "_set_cache"):
                    self._set_cache(name, skeleton)
                else:
                    self._values[name] = skeleton
                return skeleton
            # Fallback: no parsed entry - raise as before
            raise CircularWiringError(
                (
                    "Circular wiring dependency detected while resolving "
                    + repr(name)
                )
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

            # Separate positional args (int keys) from keyword args
            # (str keys) if we received a dict of parameters
            if isinstance(kwargs, dict):
                pos_args, kwargs_dict = self._separate_args_kwargs(kwargs)
            elif isinstance(kwargs, list):
                pos_args = kwargs
                kwargs_dict = {}
            else:
                pos_args = [kwargs]
                kwargs_dict = {}

            # Check if a skeleton placeholder was previously inserted for this
            # name (due to an inner circular reference). If present and still
            # partial, bind or initialize it instead of creating a new object.
            values = cast(
                Optional[dict[str, object]], getattr(self, "_values", None)
            )
            if values is not None:
                cached = values.get(name)
            else:
                cached = None
            if cached is not None and cast(
                bool, getattr(cached, "_apywire_partial", False)
            ):
                skeleton = cached
                try:
                    if entry.factory_method:
                        # Temporarily override cls.__new__ to return skeleton
                        orig_new = cast(object, getattr(cls, "__new__", None))

                        def _tmp_new(
                            _cls: type, *a: object, **k: object
                        ) -> object:
                            return skeleton

                        setattr(cls, "__new__", _tmp_new)
                        try:
                            ret = constructor(*pos_args, **kwargs_dict)
                        finally:
                            # Restore original __new__
                            if orig_new is None:
                                try:
                                    delattr(cls, "__new__")
                                except Exception:
                                    pass
                            else:
                                try:
                                    setattr(cls, "__new__", orig_new)
                                except Exception:
                                    pass

                        if ret is not skeleton:
                            exc = PartialConstructionError(
                                "factory for %r returned a different instance "
                                "than the skeleton" % (name,)
                            )
                            self._cleanup_skeleton(name, skeleton, exc)
                            raise exc

                        # Success: finalize skeleton
                        self._finalize_skeleton(skeleton, None)
                        instance = skeleton
                    else:
                        # Direct class initialization on the skeleton
                        try:
                            cast(object, cls).__init__(  # type: ignore[misc]
                                skeleton, *pos_args, **kwargs_dict
                            )
                        except Exception as e:
                            exc = PartialConstructionError(
                                "failed to initialize skeleton for %r: %s"
                                % (name, e)
                            )
                            self._cleanup_skeleton(name, skeleton, exc)
                            raise exc from e
                        # Finalize on success
                        self._finalize_skeleton(skeleton, None)
                        instance = skeleton
                except PartialConstructionError:
                    raise
                except Exception as e:
                    exc = PartialConstructionError(
                        "partial construction failed for %r: %s" % (name, e)
                    )
                    self._cleanup_skeleton(name, skeleton, exc)
                    raise exc from e
            else:
                # No skeleton present; normal instantiation
                try:
                    instance = constructor(*pos_args, **kwargs_dict)
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

        return PLACEHOLDER_REGEX.sub(replace_placeholder, template)


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
            val = self._wiring._values[self._name]
            # If this is a partial skeleton, wait for finalization
            if cast(bool, getattr(val, "_apywire_partial", False)):
                event = cast(
                    Optional[threading.Event],
                    getattr(val, "_apywire_event", None),
                )
                if event is not None:
                    event.wait()
                failure = cast(
                    Optional[Exception], getattr(val, "_apywire_failure", None)
                )
                if failure is not None:
                    raise failure
            return val
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
                "'%s' object has no attribute %r"
                % (type(self._wiring).__name__, name)
            )

        async def _get() -> object:
            # EAFP: Try cached value first
            loop = asyncio.get_running_loop()
            try:
                val = self._wiring._values[name]
                if cast(bool, getattr(val, "_apywire_partial", False)):
                    event = cast(
                        Optional[threading.Event],
                        getattr(val, "_apywire_event", None),
                    )
                    if event is not None:
                        # Run blocking wait in executor to avoid
                        # blocking the event loop
                        await loop.run_in_executor(None, event.wait)
                    failure = cast(
                        Optional[Exception],
                        getattr(val, "_apywire_failure", None),
                    )
                    if failure is not None:
                        raise failure
                return val
            except KeyError:
                pass

            # If not cached, run instantiation in executor to avoid blocking
            # the event loop.
            return await loop.run_in_executor(
                None,
                lambda: self._wiring._instantiate_attr(
                    name, lambda: self._wiring._instantiate_impl(name)
                ),
            )

        return _get
