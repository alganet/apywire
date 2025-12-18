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
from typing import Callable, Literal, NoReturn, Optional, cast

from apywire.constants import CACHE_ATTR_PREFIX
from apywire.exceptions import LockUnavailableError


class _ThreadLocalState(threading.local):
    """Thread-local storage for wiring resolution state.

    Provides typed attributes initialized per-thread:
    - resolving_stack: Stack for circular dependency detection
    - mode: Current instantiation mode ('optimistic', 'global', or None)
    - held_locks: Locks held by this thread
    """

    def __init__(self) -> None:
        super().__init__()
        self.resolving_stack: list[str] = []
        self.mode: Literal["optimistic", "global"] | None = None
        self.held_locks: list[threading.RLock] = []


class ThreadSafeMixin:
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
        # pragma: no cover - exercised via WiringRuntime
        self._inst_lock = threading.RLock()
        self._attr_locks: dict[str, threading.RLock] = {}
        self._attr_locks_lock = threading.Lock()
        self._local: _ThreadLocalState = _ThreadLocalState()
        self._max_lock_attempts = max_lock_attempts
        self._lock_retry_sleep = lock_retry_sleep

    def _get_attribute_lock(self, name: str) -> threading.RLock:
        with self._attr_locks_lock:
            if name not in self._attr_locks:
                self._attr_locks[name] = threading.RLock()
            return self._attr_locks[name]

    def _get_resolving_stack(self) -> list[str]:
        return self._local.resolving_stack

    def _get_held_locks(self) -> list[threading.RLock]:
        return self._local.held_locks

    def _release_held_locks(self) -> None:
        for lock in reversed(self._local.held_locks):
            lock.release()
        self._local.held_locks.clear()

    def _check_cache(self, name: str) -> tuple[bool, object | None]:
        """Check if attribute is cached, return (found, value) tuple.

        Checks both _values dict (if present) and _<name> attribute.
        Returns (True, value) if cached, (False, None) if not found.
        """
        cache_attr = f"{CACHE_ATTR_PREFIX}{name}"

        if hasattr(self, "_values"):
            values_dict = cast(dict[str, object], getattr(self, "_values"))
            if name in values_dict:
                val = values_dict[name]
                # If partial skeleton, wait then re-raise stored failure if any
                if cast(bool, getattr(val, "_apywire_partial", False)):
                    event = cast(
                        Optional[threading.Event],
                        getattr(val, "_apywire_event", None),
                    )
                    if event is not None:
                        event.wait()
                    failure = cast(
                        Optional[Exception],
                        getattr(val, "_apywire_failure", None),
                    )
                    if failure is not None:
                        # Re-raise stored exception for waiters
                        raise failure
                return (True, val)

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
        mode = self._local.mode
        if mode is None:
            # Try optimistic per-attribute lock; fall back to global if busy.
            if lock.acquire(blocking=False):
                try:
                    found, value = self._check_cache(name)
                    if found:
                        return value
                    # Enter optimistic mode
                    self._local.mode = "optimistic"
                    held = self._get_held_locks()
                    held.clear()
                    held.append(lock)
                    try:
                        inst = maker()
                    except LockUnavailableError:
                        # On LockUnavailableError, release and fallback
                        lock.release()
                        held.clear()
                    except Exception as e:
                        # Release lock and wrap error
                        lock.release()
                        self._wrap_instantiation_error(e, name)
                    else:
                        # Cache value
                        self._set_cache(name, inst)
                        # Release optimistic locks
                        self._release_held_locks()
                        return inst
                finally:
                    # Exit optimistic mode
                    if self._local.mode == "optimistic":
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
                # Leave locks to top-level caller
                pass
