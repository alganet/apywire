# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

import threading
import time
from typing import cast
from unittest.mock import MagicMock

import pytest

from apywire.exceptions import LockUnavailableError, WiringError
from apywire.thread_safety import CompiledThreadSafeMixin


class MockContainer(CompiledThreadSafeMixin):
    # Dynamic attributes for testing
    _bar: str
    _race: str
    _race_global: str

    def __init__(
        self, max_lock_attempts: int = 10, lock_retry_sleep: float = 0.01
    ) -> None:
        self._init_thread_safety(max_lock_attempts, lock_retry_sleep)
        self._values: dict[str, object] = {}


def test_thread_safety_init_and_helpers() -> None:
    """Test initialization and basic helpers of CompiledThreadSafeMixin."""
    container = MockContainer()

    # Test _get_resolving_stack initialization
    assert container._get_resolving_stack() == []
    assert container._get_resolving_stack() is container._get_resolving_stack()

    # Test _get_held_locks initialization
    assert container._get_held_locks() == []
    assert container._get_held_locks() is container._get_held_locks()

    # Test _release_held_locks with no locks held
    container2 = MockContainer()
    container2._release_held_locks()


def test_instantiate_attr_cache_hits() -> None:
    """Test _instantiate_attr returns cached values."""
    container = MockContainer()
    container._values["foo"] = "bar"

    maker = MagicMock()
    result = container._instantiate_attr("foo", maker)
    assert result == "bar"
    maker.assert_not_called()

    # Test attribute cache
    setattr(container, "bar", "baz")
    container._values = {}
    container._bar = "baz"
    result = container._instantiate_attr("bar", maker)
    assert result == "baz"
    maker.assert_not_called()


def test_instantiate_attr_optimistic_success() -> None:
    """Test optimistic locking success."""
    container = MockContainer()
    maker = MagicMock(return_value="created")

    result = container._instantiate_attr("new_attr", maker)

    assert result == "created"
    assert container._values["new_attr"] == "created"
    maker.assert_called_once()
    # Verify lock was released
    assert container._local.mode is None
    assert container._get_held_locks() == []


def test_instantiate_attr_optimistic_failure_fallback_global() -> None:
    """Test fallback to global lock when optimistic lock fails."""
    container = MockContainer()

    # Simulate another thread holding the attribute lock
    lock = container._get_attribute_lock("contested")

    def hold_lock_briefly() -> None:
        with lock:
            time.sleep(0.2)

    t = threading.Thread(target=hold_lock_briefly)
    t.start()
    time.sleep(0.05)  # Ensure thread has lock

    maker = MagicMock(return_value="finally_created")

    # This should fail optimistic, go to global, wait for lock, and succeed
    result = container._instantiate_attr("contested", maker)

    assert result == "finally_created"
    maker.assert_called_once()
    t.join()


def test_instantiate_attr_global_retry_timeout() -> None:
    """Test that global lock mode retries and eventually fails."""
    container = MockContainer(max_lock_attempts=2, lock_retry_sleep=0.01)

    # Simulate another thread holding the attribute lock indefinitely
    lock = container._get_attribute_lock("timeout")

    def hold_lock() -> None:
        with lock:
            time.sleep(0.1)

    t = threading.Thread(target=hold_lock)
    t.start()
    time.sleep(0.05)

    maker = MagicMock(side_effect=LockUnavailableError())

    with pytest.raises(WiringError, match="failed to instantiate 'timeout'"):
        container._instantiate_attr("timeout", maker)

    # Should fail after 3 attempts (0, 1, 2 -> exceeds max_lock_attempts=2)
    assert maker.call_count == 3
    t.join()


def test_instantiate_attr_global_retry_success() -> None:
    """Test that global lock mode retries and succeeds."""
    container = MockContainer(max_lock_attempts=5, lock_retry_sleep=0.01)

    lock = container._get_attribute_lock("retry_success")

    # Force global mode
    def hold_lock() -> None:
        with lock:
            time.sleep(0.1)

    t = threading.Thread(target=hold_lock)
    t.start()
    time.sleep(0.05)

    # Fail twice, then succeed
    effects: list[object] = [
        LockUnavailableError(),
        LockUnavailableError(),
        "success",
    ]
    maker = MagicMock(side_effect=effects)

    result = container._instantiate_attr("retry_success", maker)
    assert result == "success"
    assert maker.call_count == 3
    t.join()


def test_instantiate_attr_nested_optimistic_failure() -> None:
    """Test nested instantiation failing optimistic lock."""
    container = MockContainer()

    # Lock for child to force failure
    child_lock = container._get_attribute_lock("child")

    def hold_lock_briefly() -> None:
        with child_lock:
            time.sleep(0.2)

    t = threading.Thread(target=hold_lock_briefly)
    t.start()
    time.sleep(0.05)  # Wait for thread to get lock

    def make_child() -> str:
        return "child"

    def make_parent() -> str:
        return cast(str, container._instantiate_attr("child", make_child))

    # Parent starts optimistic, nested call fails, switches to global mode
    result = container._instantiate_attr("parent", make_parent)
    assert result == "child"
    t.join()


def test_instantiate_attr_exception_handling() -> None:
    """Test exception wrapping during instantiation."""
    container = MockContainer()

    def failing_maker() -> None:
        raise ValueError("oops")

    with pytest.raises(WiringError, match="failed to instantiate 'bad'"):
        container._instantiate_attr("bad", failing_maker)


def test_wiring_aio_lazy_init() -> None:
    """Test lazy initialization of aio property."""
    from apywire import Wiring

    wired = Wiring({}, thread_safe=False)
    # Access internal attribute to verify it's not there yet
    assert not hasattr(wired, "_aio_accessor")
    # Access property
    aio = wired.aio
    assert hasattr(wired, "_aio_accessor")
    assert wired.aio is aio


def test_wiring_resolving_stack_non_thread_safe() -> None:
    """Test resolving stack initialization in non-thread-safe mode."""
    from apywire import Wiring

    wired = Wiring({}, thread_safe=False)
    # It IS initialized in __init__ for non-thread-safe mode
    assert hasattr(wired, "_resolving_stack")
    stack = wired._get_resolving_stack()
    assert stack == []
    assert wired._get_resolving_stack() is stack


def test_compile_constant_aio() -> None:
    """Test _compile_constant_property with aio=True."""
    from apywire import Spec, Wiring

    wired = Wiring(cast(Spec, {"const": 42}), thread_safe=False)
    # We can't easily call _compile_constant_property directly as it returns
    # AST. But we can compile the whole thing and inspect the result.
    code = wired.compile(aio=True)
    # Verify it contains an async def for the constant
    assert "async def const(self):" in code
    assert "return 42" in code


def test_compile_aio_threaded_full_output() -> None:
    """Test full compiled output for aio=True and thread_safe=True."""
    from textwrap import dedent

    import black

    from apywire import Spec, Wiring

    spec: Spec = {
        "datetime.datetime birthday": {
            "day": 25,
            "month": 12,
            "year": 1990,
        }
    }
    wired = Wiring(spec, thread_safe=True)
    code = wired.compile(aio=True, thread_safe=True)

    # Format with black to match expected output
    mode = black.FileMode(line_length=79 - 12)  # Match test_compile_aio.py
    formatted_code = black.format_str(code, mode=mode)

    expected = dedent(
        """\
        from apywire.exceptions import LockUnavailableError
        from apywire.thread_safety import CompiledThreadSafeMixin
        import asyncio
        import datetime


        class Compiled(CompiledThreadSafeMixin):

            def __init__(self):
                self._init_thread_safety()

            async def birthday(self):
                if not hasattr(self, "_birthday"):
                    __val_day = 25
                    __val_month = 12
                    __val_year = 1990
                    loop = asyncio.get_running_loop()
                    self._birthday = await loop.run_in_executor(
                        None,
                        lambda: self._instantiate_attr(
                            "birthday",
                            lambda: datetime.datetime(
                                day=__val_day,
                                month=__val_month,
                                year=__val_year,
                            ),
                        ),
                    )
                return self._birthday


        compiled = Compiled()
        """
    )

    assert formatted_code == expected


def test_compile_complex_ast_replacement() -> None:
    """Test _replace_awaits_with_locals with complex structures."""
    import sys
    from types import ModuleType

    from apywire import Spec, Wiring

    # Mock module
    class MockMod(ModuleType):
        def func(self, **kwargs: object) -> object:
            return kwargs

    sys.modules["complex_ast"] = MockMod("complex_ast")

    try:
        spec: Spec = {
            "complex_ast.func root": {
                "a": {"nested": "{leaf}"},
                "b": ["{leaf}", "{leaf}"],
            },
            "complex_ast.func leaf": {},
        }
        wired = Wiring(spec, thread_safe=False)
        code = wired.compile(aio=True)

        assert "async def root(self):" in code
        assert "__val_1 =" in code
        assert "await self.leaf()" in code

    finally:
        del sys.modules["complex_ast"]


def test_instantiate_attr_no_values_mapping() -> None:
    """Test _instantiate_attr when _values mapping is missing."""

    class MockContainerNoValues(CompiledThreadSafeMixin):
        def __init__(self) -> None:
            self._init_thread_safety()
            # No _values attribute

    container = MockContainerNoValues()
    maker = MagicMock(return_value="created")
    result = container._instantiate_attr("attr", maker)
    assert result == "created"
    assert cast(str, getattr(container, "_attr")) == "created"
    assert not hasattr(container, "_values")


def test_instantiate_attr_optimistic_race_cache_hit() -> None:
    """Test cache hit after acquiring optimistic lock."""
    import threading

    container = MockContainer()
    maker = MagicMock(return_value="created")

    # We need to inject the value AFTER lock acquisition but BEFORE check.
    # Create a custom lock that injects the value when acquired

    class MockLock:
        def __init__(self) -> None:
            self._lock = threading.RLock()

        def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
            result = self._lock.acquire(blocking, timeout)
            if result:
                # Simulate another thread setting the value
                container._race = "race_won"
            return result

        def release(self) -> None:
            self._lock.release()

        def __enter__(self) -> bool:
            return self.acquire()

        def __exit__(self, *args: object) -> None:
            self.release()

    mock_lock = MockLock()

    # Inject the mock lock
    with container._attr_locks_lock:
        container._attr_locks["race"] = cast(threading.RLock, mock_lock)

    result = container._instantiate_attr("race", maker)
    assert result == "race_won"
    maker.assert_not_called()


def test_instantiate_attr_global_race_cache_hit() -> None:
    """Test cache hit after acquiring global lock."""
    container = MockContainer()
    maker = MagicMock(return_value="created")

    lock = container._get_attribute_lock("race_global")

    # Hold lock to force global mode
    def hold_lock_briefly() -> None:
        with lock:
            time.sleep(0.1)
            # Set value before releasing
            setattr(container, "_race_global", "race_global_won")

    t = threading.Thread(target=hold_lock_briefly)
    t.start()
    time.sleep(0.05)

    result = container._instantiate_attr("race_global", maker)
    assert result == "race_global_won"
    maker.assert_not_called()
    t.join()


def test_instantiate_attr_global_exception() -> None:
    """Test exception handling in global mode."""
    container = MockContainer()

    lock = container._get_attribute_lock("global_exc")

    def hold_lock_briefly() -> None:
        with lock:
            time.sleep(0.1)

    t = threading.Thread(target=hold_lock_briefly)
    t.start()
    time.sleep(0.05)

    def failing_maker() -> None:
        raise ValueError("global_oops")

    with pytest.raises(
        WiringError, match="failed to instantiate 'global_exc'"
    ):
        container._instantiate_attr("global_exc", failing_maker)
    t.join()


def test_aio_accessor_unknown_attribute() -> None:
    """Test AioAccessor raises AttributeError for unknown attribute."""
    import asyncio

    from apywire import Spec, Wiring

    wired = Wiring(cast(Spec, {}), thread_safe=False)

    async def get_unknown() -> None:
        await wired.aio.unknown()

    with pytest.raises(AttributeError, match="no attribute 'unknown'"):
        asyncio.run(get_unknown())


def test_compile_ast_recursion_call_tuple() -> None:
    """Test _replace_awaits_with_locals recursion into Call args and Tuple."""
    import sys
    from types import ModuleType

    from apywire import Spec, Wiring

    class MockMod(ModuleType):
        def func(self, *args: object, **kwargs: object) -> tuple[object, ...]:
            return args

    sys.modules["ast_rec"] = MockMod("ast_rec")

    try:
        spec: Spec = {
            "ast_rec.func wrapper": {"x": ("{leaf}", "{leaf}")},  # Tuple
            "ast_rec.func caller": {"x": ["{leaf}"]},  # List
            "ast_rec.func leaf": {},
        }
        # We want to trigger recursion in _replace_awaits_with_locals.
        # It recurses on Call, Dict, List, Tuple.
        # wired.compile calls _astify which produces these nodes.
        # Then _replace_awaits_with_locals traverses them.

        wired = Wiring(spec, thread_safe=False)
        code = wired.compile(aio=True)

        # Verify code generation handles AST recursion correctly
        assert "async def wrapper(self):" in code
        assert "async def caller(self):" in code

    finally:
        del sys.modules["ast_rec"]
