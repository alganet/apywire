# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

import asyncio
import datetime
from textwrap import dedent
from typing import Awaitable, Callable, Protocol, cast

import black
import pytest

import apywire

THREE_INDENTS = 12
BLACK_MODE = black.FileMode(line_length=79 - THREE_INDENTS)


class _DynamicAccessor(Protocol):
    """Protocol for dynamic attribute access (e.g., .aio)."""

    def __getattr__(self, name: str) -> Callable[[], Awaitable[object]]: ...


def test_aio_compile_constructor_args() -> None:
    class _Compiled(Protocol):
        def birthday(self) -> datetime.datetime: ...
        @property
        def aio(self) -> _DynamicAccessor: ...

    spec: apywire.Spec = {
        "datetime.datetime birthday": {
            "day": 25,
            "month": 12,
            "year": 1990,
        }
    }
    pythonCode = apywire.WiringCompiler(spec, thread_safe=False).compile(
        aio=True
    )
    execd: dict[str, _Compiled] = {}
    exec(pythonCode, execd)
    compiled = execd["compiled"]

    # Sync access works
    assert compiled.birthday().year == 1990

    # Async access via .aio works
    async def get() -> datetime.datetime:
        accessor = compiled.aio.birthday()
        return await cast(Awaitable[datetime.datetime], accessor)

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

    class _Compiled(Protocol):
        def wrapper(self) -> Wrapper: ...
        def other(self) -> SomeClass: ...
        @property
        def aio(self) -> _DynamicAccessor: ...

    mod = MockModule()
    sys.modules["mymod_async_c"] = mod
    try:
        spec: apywire.Spec = {
            "mymod_async_c.SomeClass other": {},
            "mymod_async_c.Wrapper wrapper": {"child": "{other}"},
        }
        pythonCode = apywire.WiringCompiler(spec, thread_safe=False).compile(
            aio=True
        )
        execd: dict[str, _Compiled] = {}
        exec(pythonCode, execd)

        compiled = execd["compiled"]
        SomeClass.inst_count = 0

        # Sync access resolves deps
        wrapper = compiled.wrapper()
        assert isinstance(wrapper, Wrapper)
        assert isinstance(wrapper.child, SomeClass)

        # Cached and reused via sync
        other_compiled = compiled.other()
        assert wrapper.child is other_compiled

        # Async access also returns cached values
        async def get_other() -> SomeClass:
            return await cast(Awaitable[SomeClass], compiled.aio.other())

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

    class _Compiled(Protocol):
        def container(self) -> ListContainer: ...
        def one(self) -> Item: ...
        def two(self) -> Item: ...

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
        pythonCode = apywire.WiringCompiler(spec, thread_safe=False).compile(
            aio=True
        )
        execd: dict[str, _Compiled] = {}
        exec(pythonCode, execd)
        compiled = execd["compiled"]

        # Sync access
        container = compiled.container()
        one = compiled.one()
        two = compiled.two()

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
    pythonCode = apywire.WiringCompiler(spec, thread_safe=False).compile(
        aio=True
    )
    pythonCode = black.format_str(pythonCode, mode=BLACK_MODE)
    assert dedent("""\
            import datetime
            from functools import cached_property
            from apywire.runtime import CompiledAio


            class Compiled:

                def birthday(self):
                    if not hasattr(self, "_birthday"):
                        self._birthday = datetime.datetime(
                            day=25, month=12, year=1990
                        )
                    return self._birthday

                @cached_property
                def aio(self):
                    return CompiledAio(self)


            compiled = Compiled()
            """) == pythonCode


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


def test_aio_compiled_constant_not_run_in_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Compiled constants skip run_in_executor, matching runtime."""
    import asyncio as aio_mod

    class _Compiled(Protocol):
        @property
        def aio(self) -> _DynamicAccessor: ...

    spec: apywire.Spec = {"myConst": 42}
    code = apywire.WiringCompiler(spec).compile(aio=True)
    execd: dict[str, _Compiled] = {}
    exec(code, execd)
    compiled = execd["compiled"]

    class DummyLoop:
        def run_in_executor(
            self, *args: object, **kwargs: object
        ) -> object:
            raise AssertionError(
                "run_in_executor should not be called"
                " for constants"
            )

    monkeypatch.setattr(
        aio_mod, "get_running_loop", lambda: DummyLoop()
    )

    async def get() -> int:
        return await cast(Awaitable[int], compiled.aio.myConst())

    result = asyncio.run(get())
    assert result == 42


@pytest.mark.parametrize(
    "class_path, args, expected",
    [
        ("builtins.int", [99], 99),
        ("builtins.complex", {0: 1.0, "imag": 2.0}, complex(1.0, 2.0)),
    ],
    ids=["int", "complex"],
)
def test_compile_aio_instantiation(
    class_path: str, args: object, expected: object
) -> None:
    """Test async compilation of various stdlib classes."""

    class _Compiled(Protocol):
        def obj(self) -> object: ...
        @property
        def aio(self) -> _DynamicAccessor: ...

    spec = {f"{class_path} obj": args}
    compiler = apywire.WiringCompiler(spec)  # type: ignore[arg-type]
    code = compiler.compile(aio=True)

    execd: dict[str, _Compiled] = {}
    exec(code, execd)
    compiled = execd["compiled"]

    # Sync access works
    val = compiled.obj()
    assert val == expected

    # Async access via .aio works
    async def run() -> None:
        aio_val = await compiled.aio.obj()
        assert aio_val == expected

    asyncio.run(run())


def test_aio_compile_sync_methods_generated() -> None:
    """Test that compile(aio=True) generates sync def methods."""
    from apywire import Spec, WiringCompiler

    spec: Spec = {
        "datetime.datetime now": {"year": 2025, "month": 1, "day": 1},
        "datetime.datetime later": {"year": 2025, "month": 6, "day": 15},
    }

    code = WiringCompiler(spec, thread_safe=False).compile(aio=True)

    # Methods are sync def, not async def
    assert "def now(self):" in code
    assert "def later(self):" in code
    assert "async def now(self):" not in code
    assert "async def later(self):" not in code

    # But aio features are present
    assert "cached_property" in code
    assert "CompiledAio" in code


def test_aio_compile_references_in_sync() -> None:
    """Test that sync methods correctly resolve {ref} placeholders."""
    import sys
    from types import ModuleType

    from apywire import Spec, WiringCompiler

    class MockMod(ModuleType):
        def combine(
            self, *args: object, **kwargs: object
        ) -> dict[str, object]:
            return {"args": args, **kwargs}

    sys.modules["nested_call"] = MockMod("nested_call")

    try:
        spec: Spec = {
            "nested_call.combine root": {
                "x": "{a}",
                "y": "{b}",
            },
            "nested_call.combine a": {},
            "nested_call.combine b": {},
        }
        code = WiringCompiler(spec, thread_safe=False).compile(aio=True)

        # Methods are sync def
        assert "def root(self):" in code
        assert "def a(self):" in code
        assert "def b(self):" in code

        # Sync refs use self.name() calls
        assert "self.a()" in code
        assert "self.b()" in code

    finally:
        del sys.modules["nested_call"]


def test_compile_constant_accessor_skip() -> None:
    """Test that constant accessors skip already-parsed items."""
    import sys
    from types import ModuleType

    from apywire import Spec, WiringCompiler

    class MockMod(ModuleType):
        pass

    sys.modules["const_test"] = MockMod("const_test")

    try:
        # Mix of parsed wired objects and constants
        spec: Spec = {
            "datetime.datetime obj": {"year": 2025, "month": 1, "day": 1},
            "const": "value",
        }
        code = WiringCompiler(spec, thread_safe=False).compile()

        # Both should be in code
        assert "def obj(self):" in code
        assert "def const(self):" in code
        assert "return 'value'" in code

    finally:
        del sys.modules["const_test"]


def test_aio_wired_ref_placeholder() -> None:
    """Test {aio.name} placeholder injects async accessor via DI."""
    import sys
    from types import ModuleType

    class Service:
        def greet(self) -> str:
            return "hello"

    class Handler:
        def __init__(self, svc: Callable[[], Awaitable[object]]) -> None:
            self.svc = svc

    class MockModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("aio_ref_test")
            self.Service = Service
            self.Handler = Handler

    class _Compiled(Protocol):
        def handler(self) -> Handler: ...

    sys.modules["aio_ref_test"] = MockModule()
    try:
        spec: apywire.Spec = {
            "aio_ref_test.Service svc": {},
            "aio_ref_test.Handler handler": {"svc": "{aio.svc}"},
        }

        # Test runtime
        wiring = apywire.Wiring(spec)
        handler = cast(Handler, wiring.handler())
        assert callable(handler.svc)

        async def run() -> None:
            resolved_svc = await handler.svc()
            assert isinstance(resolved_svc, Service)
            assert resolved_svc.greet() == "hello"

        asyncio.run(run())

        # Test compiled
        code = apywire.WiringCompiler(spec).compile(aio=True)
        assert "self.aio.svc" in code

        execd: dict[str, _Compiled] = {}
        exec(code, execd)
        compiled = execd["compiled"]
        compiled_handler = compiled.handler()
        assert callable(compiled_handler.svc)

        async def run_compiled() -> None:
            resolved_svc = await compiled_handler.svc()
            assert isinstance(resolved_svc, Service)

        asyncio.run(run_compiled())
    finally:
        if "aio_ref_test" in sys.modules:
            del sys.modules["aio_ref_test"]
