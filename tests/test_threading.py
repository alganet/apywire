# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

"""Threading-specific tests for apywire.Wiring.

These tests verify thread-safe instantiation, locking behavior, and
concurrent access patterns.
"""

import sys
import threading
from types import ModuleType
from typing import Awaitable, Protocol, cast

import pytest

import apywire
from apywire.exceptions import LockUnavailableError


class SyncSingletonProtocol(Protocol):
    def singleton(self) -> object: ...


class AsyncSingletonProtocol(Protocol):
    def singleton(self) -> Awaitable[object]: ...


def test_thread_safe_singleton_instantiation() -> None:
    """Test that multiple threads instantiating singleton."""

    class SomeClass:
        inst_count: int = 0

        def __init__(self) -> None:
            SomeClass.inst_count += 1

    class MockModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("mymod_threads")
            self.SomeClass = SomeClass

    mod = MockModule()
    sys.modules["mymod_threads"] = mod
    try:
        spec: apywire.Spec = {"mymod_threads.SomeClass singleton": {}}
        wired: apywire.Wiring = apywire.Wiring(spec, thread_safe=True)

        results: list[object] = []

        def worker(i: int) -> None:
            val = wired.singleton()
            results.append(val)

        threads: list[threading.Thread] = []
        for i in range(10):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()
        for t in threads:
            t.join()

        assert SomeClass.inst_count == 1
        # All returned objects should be the same instance
        assert all(r is results[0] for r in results)
    finally:
        if "mymod_threads" in sys.modules:
            del sys.modules["mymod_threads"]


def test_fallback_to_global_lock_avoids_double_instantiation() -> None:
    """Test that optimistic locking falls back to global lock correctly."""

    start_event = threading.Event()
    cont_event = threading.Event()

    class B:
        inst_count: int = 0

        def __init__(self) -> None:
            B.inst_count += 1
            # Block so another thread can attempt to instantiate 'a'
            start_event.set()
            cont_event.wait()

    class A:
        def __init__(self, b: object) -> None:
            self.b = b

    class MockModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("mymod_fallback")
            self.B = B
            self.A = A

    mod = MockModule()
    sys.modules["mymod_fallback"] = mod
    try:
        spec: apywire.Spec = {
            "mymod_fallback.B b": {},
            "mymod_fallback.A a": {"b": "{b}"},
        }
        wired: apywire.Wiring = apywire.Wiring(spec, thread_safe=True)

        def instantiate_b() -> None:
            _ = wired.b()

        b_thread = threading.Thread(target=instantiate_b)
        b_thread.start()

        # Wait until B.__init__ signals it started
        start_event.wait(timeout=2)

        # Now try to instantiate 'a' concurrently; the optimistic
        # per-attribute approach should fall back to the global lock and
        # not create a second instance of 'b'.
        a_thread_result: list[object] = []

        def instantiate_a() -> None:
            a_thread_result.append(wired.a())

        a_thread = threading.Thread(target=instantiate_a)
        a_thread.start()
        # Let the B initialization finish to unblock both threads
        cont_event.set()
        b_thread.join(timeout=2)
        a_thread.join(timeout=2)

        assert B.inst_count == 1
        assert a_thread_result and a_thread_result[0] is wired.a()
    finally:
        if "mymod_fallback" in sys.modules:
            del sys.modules["mymod_fallback"]


def test_forced_per_attr_lock_failure_triggers_global_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that failed per-attribute lock triggers global fallback."""

    class B:
        inst_count: int = 0

        def __init__(self) -> None:
            B.inst_count += 1

    class A:
        def __init__(self, b: object) -> None:
            self.b = b

    class MockModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("mymod_forced")
            self.B = B
            self.A = A

    mod = MockModule()
    sys.modules["mymod_forced"] = mod
    try:
        spec: apywire.Spec = {
            "mymod_forced.B b": {},
            "mymod_forced.A a": {"b": "{b}"},
        }
        wired: apywire.Wiring = apywire.Wiring(spec, thread_safe=True)

        # Force per-attribute non-blocking acquire to fail for 'a' =>
        # fallback to global lock is triggered.
        class FakeLock:
            def __init__(self) -> None:
                self._real = threading.RLock()
                self.called = False

            def acquire(self, blocking: bool = True) -> bool:
                if not blocking and not self.called:
                    self.called = True
                    return False
                return self._real.acquire(blocking)

            def release(self) -> None:
                self._real.release()

        fake = FakeLock()
        wired._attr_locks["a"] = cast(threading.RLock, fake)
        wired._attr_locks["b"] = threading.RLock()

        val = wired.a()
        assert isinstance(val, A)
        assert B.inst_count == 1
    finally:
        if "mymod_forced" in sys.modules:
            del sys.modules["mymod_forced"]


def test_lock_retry_logic_with_eventual_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that the retry logic in global instantiation mode works correctly
    when _LockUnavailableError is raised a few times before succeeding.
    """

    class SomeClass:
        def __init__(self) -> None:
            self.value = "success"

    class MockModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("mymod_retry")
            self.SomeClass = SomeClass

    mod = MockModule()
    sys.modules["mymod_retry"] = mod
    try:
        spec: apywire.Spec = {"mymod_retry.SomeClass obj": {}}
        wired: apywire.Wiring = apywire.Wiring(
            spec,
            max_lock_attempts=10,
            lock_retry_sleep=0.001,
            thread_safe=True,
        )

        # Track how many times _instantiate_impl is called
        call_count = [0]
        original_instantiate = wired._instantiate_impl

        def mock_instantiate_impl(name: str) -> object:
            call_count[0] += 1
            # Raise LockUnavailableError the first 3 times, then succeed
            if call_count[0] < 3:
                raise LockUnavailableError()
            return original_instantiate(name)

        monkeypatch.setattr(wired, "_instantiate_impl", mock_instantiate_impl)

        # Force global instantiation mode by acquiring the lock first
        lock = wired._get_attribute_lock("obj")
        lock.acquire(blocking=False)

        result = wired.obj()
        assert isinstance(result, SomeClass)
        assert result.value == "success"
        assert call_count[0] == 3  # Raised at count 1,2; succeeded at 3
    finally:
        if "mymod_retry" in sys.modules:
            del sys.modules["mymod_retry"]


def test_lock_retry_logic_exceeds_max_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that the retry logic raises WiringError when max_lock_attempts
    is exceeded.
    """

    class SomeClass:
        def __init__(self) -> None:
            self.value = "success"

    class MockModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("mymod_retry_fail")
            self.SomeClass = SomeClass

    mod = MockModule()
    sys.modules["mymod_retry_fail"] = mod
    try:
        spec: apywire.Spec = {"mymod_retry_fail.SomeClass obj": {}}
        wired: apywire.Wiring = apywire.Wiring(
            spec, max_lock_attempts=5, lock_retry_sleep=0.001, thread_safe=True
        )

        # Mock _instantiate_impl to always raise LockUnavailableError
        def mock_instantiate(*args: object) -> object:
            raise LockUnavailableError()

        monkeypatch.setattr(wired, "_instantiate_impl", mock_instantiate)

        # Force global instantiation mode
        lock = wired._get_attribute_lock("obj")
        lock.acquire(blocking=False)

        try:
            _ = wired.obj()
            assert False, "Should have raised WiringError"
        except apywire.WiringError as e:
            assert "failed to instantiate 'obj'" in str(e)
    finally:
        if "mymod_retry_fail" in sys.modules:
            del sys.modules["mymod_retry_fail"]


def test_non_threaded_mode_works() -> None:
    """Test that thread_safe=False works correctly for single-threaded use."""

    class SomeClass:
        inst_count: int = 0

        def __init__(self) -> None:
            SomeClass.inst_count += 1
            self.value = "test"

    class MockModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("mymod_nonthreaded")
            self.SomeClass = SomeClass

    mod = MockModule()
    sys.modules["mymod_nonthreaded"] = mod
    try:
        spec: apywire.Spec = {"mymod_nonthreaded.SomeClass obj": {}}
        wired: apywire.Wiring = apywire.Wiring(spec, thread_safe=False)

        # Should instantiate successfully
        result = wired.obj()
        assert isinstance(result, SomeClass)
        assert result.value == "test"
        assert SomeClass.inst_count == 1

        # Should return the same instance
        result2 = wired.obj()
        assert result2 is result
        assert SomeClass.inst_count == 1
    finally:
        if "mymod_nonthreaded" in sys.modules:
            del sys.modules["mymod_nonthreaded"]


def test_async_await_accessor_thread_safe() -> None:
    import asyncio
    import sys
    from types import ModuleType

    class SomeClass:
        inst_count: int = 0

        def __init__(self) -> None:
            SomeClass.inst_count += 1

    class MockModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("mymod_async_thread")
            self.SomeClass = SomeClass

    mod = MockModule()
    sys.modules["mymod_async_thread"] = mod
    try:
        spec: apywire.Spec = {
            "mymod_async_thread.SomeClass singleton": {},
        }
        wired: apywire.Wiring = apywire.Wiring(spec, thread_safe=True)

        async def get() -> object:
            return await wired.aio.singleton()

        instance = asyncio.run(get())
        assert isinstance(instance, SomeClass)
        # Should be cached and reused
        assert instance is wired.singleton()
    finally:
        if "mymod_async_thread" in sys.modules:
            del sys.modules["mymod_async_thread"]


def test_non_threaded_mode_circular_dependency() -> None:
    """Test that circular dependency detection works in non-threaded mode."""

    class A:
        def __init__(self, b: object) -> None:
            self.b = b

    class B:
        def __init__(self, a: object) -> None:
            self.a = a

    class MockModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("mymod_circ_nonthreaded")
            self.A = A
            self.B = B

    mod = MockModule()
    sys.modules["mymod_circ_nonthreaded"] = mod
    try:
        spec: apywire.Spec = {
            "mymod_circ_nonthreaded.A a": {"b": "{b}"},
            "mymod_circ_nonthreaded.B b": {"a": "{a}"},
        }
        wired: apywire.Wiring = apywire.Wiring(spec, thread_safe=False)
        try:
            _ = wired.a()
            assert False, "Should have raised CircularWiringError"
        except apywire.CircularWiringError as e:
            assert "Circular wiring dependency detected" in str(e)
    finally:
        if "mymod_circ_nonthreaded" in sys.modules:
            del sys.modules["mymod_circ_nonthreaded"]


def test_threaded_mode_circular_dependency() -> None:
    """Test that circular dependency detection works in threaded mode."""

    class A:
        def __init__(self, b: object) -> None:
            self.b = b

    class B:
        def __init__(self, a: object) -> None:
            self.a = a

    class MockModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("mymod_circ_threaded")
            self.A = A
            self.B = B

    mod = MockModule()
    sys.modules["mymod_circ_threaded"] = mod
    try:
        spec: apywire.Spec = {
            "mymod_circ_threaded.A a": {"b": "{b}"},
            "mymod_circ_threaded.B b": {"a": "{a}"},
        }
        wired: apywire.Wiring = apywire.Wiring(spec, thread_safe=True)
        try:
            _ = wired.a()
            assert False, "Should have raised CircularWiringError"
        except apywire.CircularWiringError as e:
            assert "Circular wiring dependency detected" in str(e)
    finally:
        if "mymod_circ_threaded" in sys.modules:
            del sys.modules["mymod_circ_threaded"]


def test_optimistic_instantiation_exception_wrapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test exception wrapping in optimistic instantiation mode."""

    class FailingClass:
        def __init__(self) -> None:
            raise ValueError("Intentional failure")

    class MockModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("mymod_fail_opt")
            self.FailingClass = FailingClass

    mod = MockModule()
    sys.modules["mymod_fail_opt"] = mod
    try:
        spec: apywire.Spec = {"mymod_fail_opt.FailingClass obj": {}}
        wired: apywire.Wiring = apywire.Wiring(spec, thread_safe=True)

        try:
            _ = wired.obj()
            assert False, "Should have raised WiringError"
        except apywire.WiringError as e:
            assert "failed to instantiate 'obj'" in str(e)
            # Check the cause chain
            assert e.__cause__ is not None
            assert isinstance(e.__cause__, ValueError)
            assert "Intentional failure" in str(e.__cause__)
    finally:
        if "mymod_fail_opt" in sys.modules:
            del sys.modules["mymod_fail_opt"]


def test_release_held_locks_when_no_locks() -> None:
    """Test _release_held_locks early return when no locks are held."""

    class SomeClass:
        def __init__(self) -> None:
            self.value = "test"

    class MockModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("mymod_no_locks")
            self.SomeClass = SomeClass

    mod = MockModule()
    sys.modules["mymod_no_locks"] = mod
    try:
        spec: apywire.Spec = {"mymod_no_locks.SomeClass obj": {}}
        wired: apywire.Wiring = apywire.Wiring(spec, thread_safe=True)

        # Call _release_held_locks when no locks are held
        # This should hit the early return on line 640
        wired._release_held_locks()

        # Should still work normally
        result = wired.obj()
        assert isinstance(result, SomeClass)
    finally:
        if "mymod_no_locks" in sys.modules:
            del sys.modules["mymod_no_locks"]


def test_wiring_error_rewrapping_in_optimistic_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that WiringError is re-wrapped in optimistic mode."""

    class Inner:
        def __init__(self) -> None:
            # This will cause a WiringError to be raised
            raise apywire.WiringError("Inner instantiation failed")

    class Outer:
        def __init__(self, inner: object) -> None:
            self.inner = inner

    class MockModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("mymod_wiring_err")
            self.Inner = Inner
            self.Outer = Outer

    mod = MockModule()
    sys.modules["mymod_wiring_err"] = mod
    try:
        spec: apywire.Spec = {
            "mymod_wiring_err.Inner inner": {},
            "mymod_wiring_err.Outer outer": {"inner": "{inner}"},
        }
        wired: apywire.Wiring = apywire.Wiring(spec, thread_safe=True)

        try:
            _ = wired.outer()
            assert False, "Should have raised WiringError"
        except apywire.WiringError as e:
            # Should be wrapped with context
            assert "failed to instantiate" in str(e)
            # Check the cause chain contains the original error
            assert e.__cause__ is not None
    finally:
        if "mymod_wiring_err" in sys.modules:
            del sys.modules["mymod_wiring_err"]


def test_compiled_thread_safe_singleton_instantiation_sync() -> None:
    import sys
    import threading
    from types import ModuleType

    class SomeClass:
        inst_count: int = 0

        def __init__(self) -> None:
            SomeClass.inst_count += 1

    class MockModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("mymod_compiled_thread")
            self.SomeClass = SomeClass

    mod = MockModule()
    sys.modules["mymod_compiled_thread"] = mod
    try:
        spec: apywire.Spec = {
            "mymod_compiled_thread.SomeClass singleton": {},
        }
        wired = apywire.Wiring(spec, thread_safe=False)
        pythonCode = wired.compile(thread_safe=True)
        execd: dict[str, object] = {}
        exec(pythonCode, execd)
        compiled_obj = cast(SyncSingletonProtocol, execd["compiled"])

        SomeClass.inst_count = 0

        def call_singleton() -> None:
            compiled_obj.singleton()

        threads = [threading.Thread(target=call_singleton) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert SomeClass.inst_count == 1
    finally:
        if "mymod_compiled_thread" in sys.modules:
            del sys.modules["mymod_compiled_thread"]


def test_compiled_thread_safe_singleton_instantiation_async() -> None:
    import asyncio
    import sys
    from types import ModuleType

    class SomeClass:
        inst_count: int = 0

        def __init__(self) -> None:
            SomeClass.inst_count += 1

    class MockModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("mymod_compiled_thread_async")
            self.SomeClass = SomeClass

    mod = MockModule()
    sys.modules["mymod_compiled_thread_async"] = mod
    try:
        spec: apywire.Spec = {
            "mymod_compiled_thread_async.SomeClass singleton": {},
        }
        wired = apywire.Wiring(spec, thread_safe=False)
        pythonCode = wired.compile(aio=True, thread_safe=True)
        execd: dict[str, object] = {}
        exec(pythonCode, execd)
        compiled_obj = cast(AsyncSingletonProtocol, execd["compiled"])

        SomeClass.inst_count = 0

        async def call_singleton() -> object:
            return await compiled_obj.singleton()

        async def run_all() -> list[object]:
            tasks = [asyncio.create_task(call_singleton()) for _ in range(8)]
            return await asyncio.gather(*tasks)

        asyncio.run(run_all())
        assert SomeClass.inst_count == 1
    finally:
        if "mymod_compiled_thread_async" in sys.modules:
            del sys.modules["mymod_compiled_thread_async"]
