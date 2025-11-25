# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

"""Thread-safety mixin for runtime and compiled wiring containers.

This module provides a mixin that both runtime Wiring and compiled Compiled
containers can inherit from to share thread-safe instantiation logic without
duplicating lock management code.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Literal, NoReturn, cast

from apywire.constants import CACHE_ATTR_PREFIX
from apywire.exceptions import LockUnavailableError


class ThreadLocalState(threading.local):
    """Typed thread-local storage for wiring resolution state.

    This class provides properly typed attributes to avoid mypy Any propagation
    when accessing dynamically-set attributes on threading.local().

    Attributes are lazily initialized per-thread:
        resolving_stack: Stack of attribute names currently being resolved
                        in this thread (for circular dependency detection).
        mode: Current instantiation mode ('optimistic', 'global', or None).
        held_locks: List of locks currently held by this thread.
    """

    resolving_stack: list[str]
    mode: Literal["optimistic", "global"] | None
    held_locks: list[threading.RLock]


class CompiledThreadSafeMixin:
    """Mixin that provides thread-safety helpers for wiring containers.

    This mixin is used by both runtime `Wiring` and compiled `Compiled`
    classes to share thread-safe instantiation logic. Call
    ``self._init_thread_safety()`` from ``__init__`` to set up required
    attributes.
    """

    # Type annotation for _values attribute (may be present on subclasses)
    _values: dict[str, object]

    def _init_thread_safety(
        self,
        max_lock_attempts: int = 10,
        lock_retry_sleep: float = 0.01,
    ) -> None:
        """Initialize thread safety primitives.

        Args:
            max_lock_attempts: maximum retry attempts in global mode
            lock_retry_sleep: sleep time between attempts
        """
        self._inst_lock = threading.RLock()
        self._attr_locks: dict[str, threading.RLock] = {}
        self._attr_locks_lock = threading.Lock()
        self._local: ThreadLocalState = ThreadLocalState()
        self._max_lock_attempts = max_lock_attempts
        self._lock_retry_sleep = lock_retry_sleep

    def _get_attribute_lock(self, name: str) -> threading.RLock:
        with self._attr_locks_lock:
            if name not in self._attr_locks:
                self._attr_locks[name] = threading.RLock()
            return self._attr_locks[name]

    def _get_resolving_stack(self) -> list[str]:
        if not hasattr(self._local, "resolving_stack"):
            self._local.resolving_stack = []
        return self._local.resolving_stack

    def _get_held_locks(self) -> list[threading.RLock]:
        if not hasattr(self._local, "held_locks"):
            self._local.held_locks = []
        return self._local.held_locks

    def _release_held_locks(self) -> None:
        if not hasattr(self._local, "held_locks"):
            return
        for lock in reversed(self._local.held_locks):
            lock.release()
        self._local.held_locks.clear()

    def _check_cache(self, name: str) -> tuple[bool, object | None]:
        """Check if attribute is cached, return (found, value) tuple.

        Checks both _values dict (if present) and _<name> attribute.
        Returns (True, value) if cached, (False, None) if not found.
        """
        cache_attr = f"{CACHE_ATTR_PREFIX}{name}"

        # Check _values dict first (runtime path)
        if hasattr(self, "_values"):
            values_dict = cast(dict[str, object], getattr(self, "_values"))
            if name in values_dict:
                return (True, values_dict[name])

        # Check cached attribute (compiled path)
        if hasattr(self, cache_attr):
            return (True, cast(object, getattr(self, cache_attr)))

        return (False, None)

    def _set_cache(self, name: str, value: object) -> None:
        """Store value in cache using appropriate storage mechanism.

        Uses _values dict if present, otherwise uses _<name> attribute.
        """
        if hasattr(self, "_values"):
            self._values[name] = value
        else:
            cache_attr = f"{CACHE_ATTR_PREFIX}{name}"
            setattr(self, cache_attr, value)

    def _wrap_instantiation_error(self, e: Exception, name: str) -> NoReturn:
        """Wrap exceptions during instantiation with proper context.

        This helper method provides consistent error wrapping for all
        instantiation paths, avoiding code duplication.

        This method always raises an exception and never returns.
        """
        from apywire.exceptions import (
            CircularWiringError,
            UnknownPlaceholderError,
            WiringError,
        )

        if isinstance(e, (UnknownPlaceholderError, CircularWiringError)):
            raise
        # All other exceptions (including WiringError) are wrapped
        raise WiringError(f"failed to instantiate '{name}'") from e

    def _instantiate_attr(
        self, name: str, maker: Callable[[], object]
    ) -> object:
        """Instantiate attribute `name` using maker() while honoring the
        optimistic/global lock policy shared with runtime Wiring.

        The `maker` callable is executed to instantiate the value when the
        thread-safe locking logic permits it to run. Returns the cached
        attribute (``self._<name>``) if already present.
        """
        # Check cache first
        found, value = self._check_cache(name)
        if found:
            return value

        lock = self._get_attribute_lock(name)
        mode: str | None = getattr(self._local, "mode", None)
        if mode is None:
            # Optimistic locking: Try to acquire per-attribute lock without
            # blocking. If successful, instantiate in optimistic mode.
            # If not, fall back to global lock.
            if lock.acquire(blocking=False):
                try:
                    found, value = self._check_cache(name)
                    if found:
                        return value
                    # Enter optimistic mode and track held locks to allow
                    # nested instantiation to detect per-attribute
                    # conflicts.
                    self._local.mode = "optimistic"
                    held = self._get_held_locks()
                    held.clear()
                    held.append(lock)
                    try:
                        inst = maker()
                    except LockUnavailableError:
                        # On optimistic failure, release the lock and fall
                        # through to global path
                        lock.release()
                        held.clear()
                    except Exception as e:
                        # Release lock before propagating exception
                        lock.release()
                        self._wrap_instantiation_error(e, name)
                    else:
                        # Store in cache
                        self._set_cache(name, inst)
                        # Release the optimistic held locks before returning
                        self._release_held_locks()
                        return inst
                finally:
                    # Clean up optimistic mode when exiting top-level call
                    if (
                        cast(
                            Literal["optimistic", "global"] | None,
                            getattr(self._local, "mode", None),
                        )
                        == "optimistic"
                    ):
                        self._local.mode = None

            # fallback to global
            with self._inst_lock:
                self._local.mode = "global"
                lock.acquire()
                try:
                    held = self._get_held_locks()
                    held.clear()
                    held.append(lock)
                    attempts = 0
                    while True:
                        try:
                            found, value = self._check_cache(name)
                            if found:
                                return value
                            inst = maker()
                            self._set_cache(name, inst)
                            return inst
                        except LockUnavailableError:
                            attempts += 1
                            if attempts > self._max_lock_attempts:
                                from apywire.exceptions import WiringError

                                raise WiringError(
                                    f"failed to instantiate '{name}'"
                                )
                            time.sleep(self._lock_retry_sleep)
                        except Exception as e:
                            self._wrap_instantiation_error(e, name)
                finally:
                    self._release_held_locks()
                    self._local.mode = None
        else:
            # Nested invocation within an existing instantiation:
            # Use per-attr lock in optimistic mode or global lock if already
            # in global mode
            if mode == "optimistic":
                if not lock.acquire(blocking=False):
                    raise LockUnavailableError()
            else:
                lock.acquire()
            held = self._get_held_locks()
            held.append(lock)
            try:
                found, value = self._check_cache(name)
                if found:
                    return value
                inst = maker()
                self._set_cache(name, inst)
                return inst
            finally:
                # Locks are intentionally not released here; they will be
                # released by the top-level caller that initiated the
                # instantiation chain
                pass
