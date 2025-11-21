# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

import datetime
from textwrap import dedent
from typing import Protocol

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
    wired: apywire.Wiring = apywire.Wiring(spec)
    instance = wired.yearsAgo
    assert isinstance(instance, datetime.datetime)
    assert instance.year == 2003
    assert instance.month == 12
    assert instance.day == 13
    assert instance is wired.yearsAgo


def test_simple_raise_on_nonexistent_wired_attribute() -> None:
    try:
        apywire.Wiring({}).nonexistent
        assert False, "Should have raised AttributeError"
    except AttributeError as e:
        assert "no attribute 'nonexistent'" in str(e)


def test_empty_class_compiled() -> None:
    wired: apywire.Wiring = apywire.Wiring({})
    pythonCode = wired.compile()
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

    wired: apywire.Wiring = apywire.Wiring(spec)
    pythonCode = wired.compile()
    pythonCode = black.format_str(pythonCode, mode=BLACK_MODE)
    assert (
        dedent(
            """\
            import datetime


            class Compiled:

                @property
                def birthday(self):
                    return datetime.datetime(day=25, month=12, year=1990)


            compiled = Compiled()
            """
        )
        == pythonCode
    )

    class MockHasBirthday(Protocol):
        birthday: datetime.datetime

    execd: dict[str, MockHasBirthday] = {}
    exec(pythonCode, execd)
    compiled = execd["compiled"]

    instance = compiled.birthday
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
        wired: apywire.Wiring = apywire.Wiring(spec)
        instance = wired.someModule
        assert isinstance(instance, SomeClass)
        assert instance.value == "deep mock"

        # Test compilation
        pythonCode = wired.compile()
        pythonCode = black.format_str(pythonCode, mode=BLACK_MODE)
        expected = dedent(
            """\
            import foo.bar.baz.bat


            class Compiled:

                @property
                def someModule(self):
                    return foo.bar.baz.bat.SomeClass()


            compiled = Compiled()
            """
        )
        assert expected == pythonCode

        class MockHasSomeModule(Protocol):
            someModule: SomeClass

        # Test execution of compiled code
        execd: dict[str, MockHasSomeModule] = {}
        exec(pythonCode, execd)
        compiled: MockHasSomeModule = execd["compiled"]
        instance = compiled.someModule
        assert isinstance(instance, SomeClass)
        assert instance.value == "deep mock"
    finally:
        # Clean up mock modules
        for mod in ["foo", "foo.bar", "foo.bar.baz", "foo.bar.baz.bat"]:
            if mod in sys.modules:
                del sys.modules[mod]
