# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

import datetime
from textwrap import dedent
from typing import Protocol, cast

import black

import apywire

THREE_INDENTS = 12
BLACK_MODE = black.FileMode(line_length=79 - THREE_INDENTS)


def test_simple_load_constructor_args() -> None:
    spec: apywire.Spec = {
        "datetime.datetime yearsAgo": {
            "day": 13,
            "month": 12,
            "year": 2003,
        }
    }
    wired: apywire.Wiring = apywire.Wiring(spec, thread_safe=False)
    instance = wired.yearsAgo()
    assert isinstance(instance, datetime.datetime)
    assert instance.year == 2003
    assert instance.month == 12
    assert instance.day == 13
    assert instance is wired.yearsAgo()


def test_simple_raise_on_nonexistent_wired_attribute() -> None:
    try:
        apywire.Wiring({}, thread_safe=False).nonexistent()
        assert False, "Should have raised AttributeError"
    except AttributeError as e:
        assert "no attribute 'nonexistent'" in str(e)


def test_empty_class_compiled() -> None:
    pythonCode = apywire.WiringCompiler({}, thread_safe=False).compile()
    pythonCode = black.format_str(pythonCode, mode=BLACK_MODE)
    assert (
        dedent(
            """\
        class Compiled:
            pass


        compiled = Compiled()
        """
        )
        == pythonCode
    )


def test_simple_compile_constructor_args() -> None:
    spec: apywire.Spec = {
        "datetime.datetime birthday": {
            "day": 25,
            "month": 12,
            "year": 1990,
        }
    }

    pythonCode = apywire.WiringCompiler(spec, thread_safe=False).compile()
    pythonCode = black.format_str(pythonCode, mode=BLACK_MODE)
    assert (
        dedent(
            """\
            import datetime


            class Compiled:

                def birthday(self):
                    if not hasattr(self, "_birthday"):
                        self._birthday = datetime.datetime(
                            day=25, month=12, year=1990
                        )
                    return self._birthday


            compiled = Compiled()
            """
        )
        == pythonCode
    )

    class MockHasBirthday(Protocol):
        def birthday(self) -> datetime.datetime: ...

    execd: dict[str, MockHasBirthday] = {}
    exec(pythonCode, execd)
    compiled = execd["compiled"]

    instance = compiled.birthday()
    assert isinstance(instance, datetime.datetime)
    assert instance.year == 1990
    assert instance.month == 12
    assert instance.day == 25


def test_deep_module_paths() -> None:
    """Test wiring with deeply nested module paths."""
    import sys
    from types import ModuleType

    # Define typed mock modules
    class SomeClass:
        def __init__(self) -> None:
            self.value = "deep mock"

    class MockBatModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("foo.bar.baz.bat")
            self.SomeClass = SomeClass

    class MockBazModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("foo.bar.baz")
            self.bat = MockBatModule()

    class MockBarModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("foo.bar")
            self.baz = MockBazModule()

    class MockFooModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("foo")
            self.bar = MockBarModule()

    # Create and set mock modules
    foo_mod = MockFooModule()
    sys.modules["foo"] = foo_mod
    sys.modules["foo.bar"] = foo_mod.bar
    sys.modules["foo.bar.baz"] = foo_mod.bar.baz
    sys.modules["foo.bar.baz.bat"] = foo_mod.bar.baz.bat

    try:
        spec: apywire.Spec = {"foo.bar.baz.bat.SomeClass someModule": {}}
        wired: apywire.Wiring = apywire.Wiring(spec, thread_safe=False)
        instance = wired.someModule()
        assert isinstance(instance, SomeClass)
        assert instance.value == "deep mock"

        # Test compilation
        pythonCode = apywire.WiringCompiler(spec, thread_safe=False).compile()
        pythonCode = black.format_str(pythonCode, mode=BLACK_MODE)
        expected = dedent(
            """\
            import foo.bar.baz.bat


            class Compiled:

                def someModule(self):
                    if not hasattr(self, "_someModule"):
                        self._someModule = foo.bar.baz.bat.SomeClass()
                    return self._someModule


            compiled = Compiled()
            """
        )
        assert expected == pythonCode

        class MockHasSomeModule(Protocol):
            def someModule(self) -> SomeClass: ...

        # Test execution of compiled code
        execd: dict[str, MockHasSomeModule] = {}
        exec(pythonCode, execd)
        compiled: MockHasSomeModule = execd["compiled"]
        instance = compiled.someModule()
        assert isinstance(instance, SomeClass)
        assert instance.value == "deep mock"
    finally:
        # Clean up mock modules
        for mod in ["foo", "foo.bar", "foo.bar.baz", "foo.bar.baz.bat"]:
            if mod in sys.modules:
                del sys.modules[mod]


def test_simple_reuse_wired_variable() -> None:
    spec: apywire.Spec = {
        "myYearValue": 2003,
        "datetime.datetime yearsAgo": {
            "day": 13,
            "month": 12,
            "year": "{myYearValue}",
        },
    }
    wired: apywire.Wiring = apywire.Wiring(spec, thread_safe=False)
    instance = wired.yearsAgo()
    assert isinstance(instance, datetime.datetime)
    assert instance.year == 2003
    assert instance.month == 12
    assert instance.day == 13
    assert instance is wired.yearsAgo()


def test_compile_constants_and_references() -> None:
    spec: apywire.Spec = {
        "myYearValue": 2003,
        "datetime.datetime yearsAgo": {
            "day": 13,
            "month": 12,
            "year": "{myYearValue}",
        },
    }
    pythonCode = apywire.WiringCompiler(spec, thread_safe=False).compile()
    pythonCode = black.format_str(pythonCode, mode=BLACK_MODE)
    assert (
        dedent(
            """\
            import datetime


            class Compiled:

                def yearsAgo(self):
                    if not hasattr(self, "_yearsAgo"):
                        self._yearsAgo = datetime.datetime(
                            day=13, month=12, year=self.myYearValue()
                        )
                    return self._yearsAgo

                def myYearValue(self):
                    return 2003


            compiled = Compiled()
            """
        )
        == pythonCode
    )

    class CompiledMock(Protocol):
        def myYearValue(self) -> int: ...
        def yearsAgo(self) -> datetime.datetime: ...

    execd: dict[str, CompiledMock] = {}
    exec(pythonCode, execd)
    compiled: CompiledMock = execd["compiled"]
    assert compiled.myYearValue() == 2003
    instance = compiled.yearsAgo()
    assert isinstance(instance, datetime.datetime)
    assert instance.year == 2003


def test_compile_inlines_mutated_values() -> None:
    # compile() should inline the current value found in _values for constants
    spec: apywire.Spec = {
        "myYearValue": 2003,
        "datetime.datetime yearsAgo": {
            "day": 13,
            "month": 12,
            "year": "{myYearValue}",
        },
    }
    compiler = apywire.WiringCompiler(spec, thread_safe=False)
    # Mutate the cached value directly and ensure compile picks it up
    compiler._values["myYearValue"] = 1999
    pythonCode = compiler.compile()
    pythonCode = black.format_str(pythonCode, mode=BLACK_MODE)
    assert (
        dedent(
            """\
            import datetime


            class Compiled:

                def yearsAgo(self):
                    if not hasattr(self, "_yearsAgo"):
                        self._yearsAgo = datetime.datetime(
                            day=13, month=12, year=self.myYearValue()
                        )
                    return self._yearsAgo

                def myYearValue(self):
                    return 1999


            compiled = Compiled()
            """
        )
        == pythonCode
    )


def test_compile_uses_self_for_non_constants() -> None:
    # Non-constant wired references should compile to `self.<name>`
    import sys
    from types import ModuleType

    class SomeClass:
        def __init__(self) -> None:
            self.value = "ok"

    class Wrapper:
        def __init__(self, child: object) -> None:
            self.child = child

    class MockModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("mymod")
            self.SomeClass = SomeClass
            self.Wrapper = Wrapper

    mod = MockModule()
    sys.modules["mymod"] = mod
    try:
        spec: apywire.Spec = {
            "mymod.SomeClass other": {},
            "mymod.Wrapper wrapper": {"child": "{other}"},
        }
        pythonCode = apywire.WiringCompiler(spec, thread_safe=False).compile()
        pythonCode = black.format_str(pythonCode, mode=BLACK_MODE)
        expected = dedent(
            """\
            import mymod


            class Compiled:

                def other(self):
                    if not hasattr(self, "_other"):
                        self._other = mymod.SomeClass()
                    return self._other

                def wrapper(self):
                    if not hasattr(self, "_wrapper"):
                        self._wrapper = mymod.Wrapper(child=self.other())
                    return self._wrapper


            compiled = Compiled()
            """
        )
        assert expected == pythonCode
    finally:
        if "mymod" in sys.modules:
            del sys.modules["mymod"]


def test_placeholder_lazy_instantiation_singleton_runtime() -> None:
    """Placeholders that refer to other wired objects should not cause
    multiple instantiations; the referenced wired object is lazily created
    and reused for multiple consumers.
    """
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
            super().__init__("mymod2")
            self.SomeClass = SomeClass
            self.Wrapper = Wrapper

    mod = MockModule()
    sys.modules["mymod2"] = mod
    try:
        spec: apywire.Spec = {
            "mymod2.SomeClass other": {},
            "mymod2.Wrapper wrapper": {"child": "{other}"},
        }
        wired: apywire.Wiring = apywire.Wiring(spec, thread_safe=False)

        # No instantiation happened yet
        assert SomeClass.inst_count == 0

        # Accessing the referenced value creates the instance
        other = wired.other()
        assert SomeClass.inst_count == 1

        # Accessing the wrapper should NOT cause another instantiation
        class HasChild(Protocol):
            child: SomeClass

        wrapper: HasChild = cast(HasChild, wired.wrapper())
        assert SomeClass.inst_count == 1
        assert wrapper.child is other

        # Re-accessing either should not increase instantiation count
        _ = wired.wrapper()
        _ = wired.other()
        assert SomeClass.inst_count == 1
    finally:
        if "mymod2" in sys.modules:
            del sys.modules["mymod2"]


def test_compiled_singleton_instantiation() -> None:
    """Compiled code should honor lazy instantiation and caching.

    Ensure single instantiation and reuse across properties, matching the
    runtime `Wiring` behavior.
    """
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
            super().__init__("mymod3")
            self.SomeClass = SomeClass
            self.Wrapper = Wrapper

    mod = MockModule()
    sys.modules["mymod3"] = mod
    try:
        spec: apywire.Spec = {
            "mymod3.SomeClass other": {},
            "mymod3.Wrapper wrapper": {"child": "{other}"},
        }
        pythonCode = apywire.WiringCompiler(spec, thread_safe=False).compile()
        pythonCode = black.format_str(pythonCode, mode=BLACK_MODE)

        # No instantiation before executing compiled code
        SomeClass.inst_count = 0
        execd: dict[str, object] = {}
        exec(pythonCode, execd)

        class CompiledProt(Protocol):
            def other(self) -> SomeClass: ...
            def wrapper(self) -> Wrapper: ...

        compiled: CompiledProt = cast(CompiledProt, execd["compiled"])

        assert SomeClass.inst_count == 0

        other = compiled.other()
        # after accessing other, we should have one instantiation
        assert SomeClass.inst_count == 1

        # `compiled` is now typed via CompiledProt above
        wrapper = compiled.wrapper()
        # wrapper access should not cause a second instantiation
        assert SomeClass.inst_count == 1
        assert wrapper.child is other

        # re-accessing compiled wrappers or values should not create more
        _ = compiled.wrapper()
        _ = compiled.other()
        assert SomeClass.inst_count == 1
    finally:
        if "mymod3" in sys.modules:
            del sys.modules["mymod3"]


def test_nested_structures_compiled_and_runtime() -> None:
    """Ensure nested lists/dicts of wired references are handled equally
    by runtime Wiring and compiled code.
    """
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
            super().__init__("mymod4")
            self.Item = Item
            self.ListContainer = ListContainer

    mod = MockModule()
    sys.modules["mymod4"] = mod
    try:
        spec: apywire.Spec = {
            "mymod4.Item one": {"value": 1},
            "mymod4.Item two": {"value": 2},
            "mymod4.ListContainer container": {
                "items": ["{one}", "{two}", 3],
                "lookup": {"a": "{one}", "b": 2},
            },
        }
        wired: apywire.Wiring = apywire.Wiring(spec, thread_safe=False)

        # Check runtime behavior
        other_one = wired.one()
        other_two = wired.two()
        container: ListContainer = cast(ListContainer, wired.container())
        assert container.items[0] is other_one
        assert container.items[1] is other_two
        assert container.items[2] == 3
        assert container.lookup["a"] is other_one
        assert container.lookup["b"] == 2

        # Check compiled behavior mirrors runtime
        pythonCode = apywire.WiringCompiler(spec, thread_safe=False).compile()
        pythonCode = black.format_str(pythonCode, mode=BLACK_MODE)
        execd: dict[str, object] = {}
        exec(pythonCode, execd)
        compiled_raw = execd["compiled"]

        class CompiledProt(Protocol):
            def one(self) -> Item: ...
            def two(self) -> Item: ...
            def container(self) -> ListContainer: ...

        compiled: CompiledProt = cast(CompiledProt, compiled_raw)
        assert compiled.one().value == 1
        assert compiled.two().value == 2
        compiled_container = compiled.container()
        assert compiled_container.items[0] is compiled.one()
        assert compiled_container.items[1] is compiled.two()
        assert compiled_container.items[2] == 3
        assert compiled_container.lookup["a"] is compiled.one()
        assert compiled_container.lookup["b"] == 2
    finally:
        if "mymod4" in sys.modules:
            del sys.modules["mymod4"]


def test_unknown_placeholder_raises() -> None:
    spec: apywire.Spec = {"datetime.datetime x": {"year": "{doesNotExist}"}}
    wired: apywire.Wiring = apywire.Wiring(spec, thread_safe=False)
    try:
        _ = wired.x()
        assert (
            False
        ), "Should have raised UnknownPlaceholderError for unknown placeholder"
    except apywire.UnknownPlaceholderError as e:
        assert "Unknown placeholder 'doesNotExist'" in str(e)


def test_async_await_accessor_simple() -> None:
    import asyncio

    spec: apywire.Spec = {
        "datetime.datetime yearsAgo": {
            "day": 13,
            "month": 12,
            "year": 2003,
        }
    }
    wired: apywire.Wiring = apywire.Wiring(spec, thread_safe=False)

    async def get() -> object:
        return await wired.aio.yearsAgo()

    instance = asyncio.run(get())
    assert isinstance(instance, datetime.datetime)
    assert instance.year == 2003
    assert instance.month == 12
    assert instance.day == 13
    # Ensure subsequent sync access returns the same cached object
    assert instance is wired.yearsAgo()


def test_async_await_accessor_references() -> None:
    import asyncio
    import sys
    from types import ModuleType

    class SomeClass:
        pass

    class Wrapper:
        def __init__(self, child: object) -> None:
            self.child = child

    class MockModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("mymod_async")
            self.SomeClass = SomeClass
            self.Wrapper = Wrapper

    mod = MockModule()
    sys.modules["mymod_async"] = mod
    try:
        spec: apywire.Spec = {
            "mymod_async.SomeClass other": {},
            "mymod_async.Wrapper wrapper": {"child": "{other}"},
        }
        wired: apywire.Wiring = apywire.Wiring(spec, thread_safe=False)

        async def get() -> object:
            # Awaiting the async wrapper should resolve placeholders as well
            return await wired.aio.wrapper()

        wrapper = asyncio.run(get())
        assert isinstance(wrapper, Wrapper)
        assert isinstance(wrapper.child, SomeClass)
        # Ensure the referenced instance is cached and reused
        assert wrapper.child is wired.other()
    finally:
        if "mymod_async" in sys.modules:
            del sys.modules["mymod_async"]


def test_circular_reference_raises() -> None:
    import sys
    from types import ModuleType

    class A:
        def __init__(self, b: object) -> None:
            self.b = b

    class B:
        def __init__(self, a: object) -> None:
            self.a = a

    class MockModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("mymod_circ")
            self.A = A
            self.B = B

    mod = MockModule()
    sys.modules["mymod_circ"] = mod
    try:
        spec: apywire.Spec = {
            "mymod_circ.A a": {"b": "{b}"},
            "mymod_circ.B b": {"a": "{a}"},
        }
        try:
            apywire.Wiring(spec, thread_safe=False)
            assert False, "Should have raised CircularWiringError at init"
        except apywire.CircularWiringError as e:
            assert "Circular dependency detected" in str(e)
    finally:
        if "mymod_circ" in sys.modules:
            del sys.modules["mymod_circ"]


def test_empty_module_name_raises() -> None:
    # Keys like "Class name" (no module) are invalid; the change should
    # raise a ValueError during parsing.
    try:
        apywire.Wiring({"Class name": {}}, thread_safe=False)
        assert False, "Should have raised ValueError for empty module name"
    except ValueError as e:
        assert "invalid spec key 'Class name'" in str(e)


def test_unknown_placeholder_exception_during_creation() -> None:
    """If creating a referenced attribute raises AttributeError, the
    resolution should translate that into a meaningful 'unknown
    placeholder' error message.
    """
    import sys
    from types import ModuleType

    class Ref:
        def __init__(self) -> None:
            raise AttributeError("creation failed")

    class Wrapper:
        def __init__(self, child: object) -> None:
            self.child = child

    class MockModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("mymod_err")
            self.Ref = Ref
            self.Wrapper = Wrapper

    mod = MockModule()
    sys.modules["mymod_err"] = mod
    try:
        spec: apywire.Spec = {
            "mymod_err.Ref ref": {},
            "mymod_err.Wrapper wrapper": {"child": "{ref}"},
        }
        wired: apywire.Wiring = apywire.Wiring(spec, thread_safe=False)
        try:
            _ = wired.wrapper()
            assert (
                False
            ), "Should have raised WiringError due to creation error"
        except apywire.WiringError as e:
            # Check that the failure is wrapped in WiringError and the
            # original constructor failure is attached as a cause. We
            # walk the exception chain to find the original constructor
            # AttributeError and confirm it contains the expected text.
            assert "failed to instantiate 'wrapper'" in str(
                e
            ) or "failed to instantiate 'ref'" in str(e)
            cause: BaseException = e
            while cause.__cause__ is not None:
                cause = cause.__cause__
            assert isinstance(cause, AttributeError)
            assert "creation failed" in str(cause)
    finally:
        if "mymod_err" in sys.modules:
            del sys.modules["mymod_err"]
