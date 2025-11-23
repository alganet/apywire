# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

import asyncio
from textwrap import dedent
from typing import Awaitable, Protocol, cast

import black
import pytest

import apywire

THREE_INDENTS = 12
BLACK_MODE = black.FileMode(line_length=79 - THREE_INDENTS)


def test_aio_compile_constructor_args() -> None:
    spec: apywire.Spec = {
        "datetime.datetime birthday": {
            "day": 25,
            "month": 12,
            "year": 1990,
        }
    }
    wired: apywire.Wiring = apywire.Wiring(spec, thread_safe=False)
    pythonCode = wired.compile(aio=True)
    execd: dict[str, object] = {}
    exec(pythonCode, execd)
    compiled = execd["compiled"]
    import datetime

    class CompiledProto(Protocol):
        def birthday(self) -> Awaitable[datetime.datetime]: ...

    compiled = cast(CompiledProto, compiled)

    async def get() -> datetime.datetime:
        return await compiled.birthday()

    instance = asyncio.run(get())
    assert instance.year == 1990


def test_aio_compile_references_and_caching() -> None:
    import sys
    from types import ModuleType

    class SomeClass:
        inst_count: int = 0

        def __init__(self) -> None:
            SomeClass.inst_count += 1

    class Wrapper:
        def __init__(self, child: object) -> None:
            self.child = child

    class MockModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("mymod_async_c")
            self.SomeClass = SomeClass
            self.Wrapper = Wrapper

    mod = MockModule()
    sys.modules["mymod_async_c"] = mod
    try:
        spec: apywire.Spec = {
            "mymod_async_c.SomeClass other": {},
            "mymod_async_c.Wrapper wrapper": {"child": "{other}"},
        }
        wired = apywire.Wiring(spec, thread_safe=False)
        pythonCode = wired.compile(aio=True)
        execd: dict[str, object] = {}
        exec(pythonCode, execd)

        class CompiledProt(Protocol):
            def other(self) -> Awaitable[SomeClass]: ...
            def wrapper(self) -> Awaitable[Wrapper]: ...

        compiled = cast(CompiledProt, execd["compiled"])
        SomeClass.inst_count = 0

        async def get_wrapper() -> Wrapper:
            return await compiled.wrapper()

        wrapper = asyncio.run(get_wrapper())
        assert isinstance(wrapper, Wrapper)
        assert isinstance(wrapper.child, SomeClass)

        # Ensure the referenced instance is cached and reused
        async def get_other_compiled() -> SomeClass:
            return await compiled.other()

        other_compiled = asyncio.run(get_other_compiled())
        assert wrapper.child is other_compiled

        # Note: compiled.other() is async and cached; verify by awaiting twice
        async def get_other() -> SomeClass:
            return await compiled.other()

        other_inst = asyncio.run(get_other())
        assert other_inst is wrapper.child
    finally:
        if "mymod_async_c" in sys.modules:
            del sys.modules["mymod_async_c"]


def test_aio_compile_nested_structures() -> None:
    import sys
    from types import ModuleType

    class Item:
        def __init__(self, value: int) -> None:
            self.value = value

    class ListContainer:
        def __init__(
            self,
            items: list[object],
            lookup: dict[str, object],
        ) -> None:
            self.items = items
            self.lookup = lookup

    class MockModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("mymod_aio")
            self.Item = Item
            self.ListContainer = ListContainer

    mod = MockModule()
    sys.modules["mymod_aio"] = mod
    try:
        spec: apywire.Spec = {
            "mymod_aio.Item one": {"value": 1},
            "mymod_aio.Item two": {"value": 2},
            "mymod_aio.ListContainer container": {
                "items": ["{one}", "{two}", 3],
                "lookup": {"a": "{one}", "b": 2},
            },
        }
        wired: apywire.Wiring = apywire.Wiring(spec, thread_safe=False)

        # Check compiled aio behavior
        pythonCode = wired.compile(aio=True)
        execd: dict[str, object] = {}
        exec(pythonCode, execd)
        compiled_raw = execd["compiled"]

        class CompiledProt(Protocol):
            def one(self) -> Awaitable[Item]: ...
            def two(self) -> Awaitable[Item]: ...
            def container(self) -> Awaitable[ListContainer]: ...

        compiled: CompiledProt = cast(CompiledProt, compiled_raw)

        async def get_container() -> ListContainer:
            return await compiled.container()

        container = asyncio.run(get_container())

        # Access via compiled.one() should be awaited
        async def get_one() -> Item:
            return await compiled.one()

        one = asyncio.run(get_one())

        async def get_two() -> Item:
            return await compiled.two()

        two = asyncio.run(get_two())
        assert container.items[0] is one
        assert container.items[1] is two
        assert container.items[2] == 3
        assert container.lookup["a"] is one
        assert container.lookup["b"] == 2
    finally:
        if "mymod_aio" in sys.modules:
            del sys.modules["mymod_aio"]


def test_aio_compile_constructor_args_source() -> None:
    spec: apywire.Spec = {
        "datetime.datetime birthday": {
            "day": 25,
            "month": 12,
            "year": 1990,
        }
    }
    wired: apywire.Wiring = apywire.Wiring(spec, thread_safe=False)
    pythonCode = wired.compile(aio=True)
    pythonCode = black.format_str(pythonCode, mode=BLACK_MODE)
    assert (
        dedent(
            """\
            import asyncio
            import datetime


            class Compiled:

                async def birthday(self):
                    if not hasattr(self, "_birthday"):
                        __val_day = 25
                        __val_month = 12
                        __val_year = 1990
                        loop = asyncio.get_running_loop()
                        self._birthday = await loop.run_in_executor(
                            None,
                            lambda: datetime.datetime(
                                day=__val_day,
                                month=__val_month,
                                year=__val_year,
                            ),
                        )
                    return self._birthday


            compiled = Compiled()
            """
        )
        == pythonCode
    )


def test_aio_accessor_constant_not_run_in_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    spec: apywire.Spec = {"myConst": 42}
    wired: apywire.Wiring = apywire.Wiring(spec, thread_safe=False)

    class DummyLoop:
        def run_in_executor(self, *args: object, **kwargs: object) -> object:
            raise AssertionError(
                "run_in_executor should not be called for constants"
            )

    monkeypatch.setattr(asyncio, "get_running_loop", lambda: DummyLoop())

    async def get() -> int:
        return await cast(Awaitable[int], wired.aio.myConst())

    result = asyncio.run(get())
    assert result == 42


def test_compile_aio_list_args() -> None:
    """Test async compilation of list arguments."""
    spec: apywire.Spec = {"builtins.int myInt": [99]}
    wired = apywire.Wiring(spec)
    # Compile with aio=True
    code = wired.compile(aio=True)

    execd: dict[str, object] = {"asyncio": asyncio}
    exec(code, execd)
    compiled = execd["compiled"]

    async def run() -> None:
        # When compiled with aio=True, the methods themselves are async
        coro = cast(Awaitable[int], getattr(compiled, "myInt")())
        val = await coro
        assert val == 99

    asyncio.run(run())


def test_compile_aio_mixed_args() -> None:
    """Test async compilation of mixed numeric/string keys."""
    spec: apywire.Spec = {"builtins.complex myComplex": {0: 1.0, "imag": 2.0}}
    wired = apywire.Wiring(spec)
    code = wired.compile(aio=True)

    execd: dict[str, object] = {"asyncio": asyncio}
    exec(code, execd)
    compiled = execd["compiled"]

    async def run() -> None:
        coro = cast(Awaitable[complex], getattr(compiled, "myComplex")())
        val = await coro
        assert val == complex(1.0, 2.0)

    asyncio.run(run())
