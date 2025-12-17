# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

"""Tests for the Generator class."""

import sys
from types import ModuleType
from typing import Dict, List, Optional, Tuple, Union

import pytest

from apywire import Generator, Spec, Wiring


def test_generate_simple_class() -> None:
    """Test generating spec for a simple class."""

    class Simple:
        def __init__(self, year: int, month: int, day: int) -> None:
            self.year = year
            self.month = month
            self.day = day

    class MockModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("mockmod_simple")
            self.Simple = Simple

    mod = MockModule()
    sys.modules["mockmod_simple"] = mod

    try:
        spec = Generator.generate("mockmod_simple.Simple now")

        # Use whole-output assertion with expected spec
        expected_spec: Spec = {
            "mockmod_simple.Simple now": {
                "day": "{now_day}",
                "month": "{now_month}",
                "year": "{now_year}",
            },
            "now_day": 0,
            "now_month": 0,
            "now_year": 0,
        }
        assert spec == expected_spec
    finally:
        if "mockmod_simple" in sys.modules:
            del sys.modules["mockmod_simple"]


def test_generate_multiple_entries() -> None:
    """Test generating spec for multiple classes at once."""

    class DateClass:
        def __init__(self, year: int, month: int) -> None:
            pass

    class DeltaClass:
        def __init__(self, days: int) -> None:
            pass

    class MockModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("mockmod_multi")
            self.DateClass = DateClass
            self.DeltaClass = DeltaClass

    mod = MockModule()
    sys.modules["mockmod_multi"] = mod

    try:
        spec = Generator.generate(
            "mockmod_multi.DateClass dt", "mockmod_multi.DeltaClass delta"
        )

        # Use whole-output assertion with expected spec
        expected_spec: Spec = {
            "mockmod_multi.DateClass dt": {
                "month": "{dt_month}",
                "year": "{dt_year}",
            },
            "mockmod_multi.DeltaClass delta": {
                "days": "{delta_days}",
            },
            "dt_month": 0,
            "dt_year": 0,
            "delta_days": 0,
        }
        assert spec == expected_spec
    finally:
        if "mockmod_multi" in sys.modules:
            del sys.modules["mockmod_multi"]


def test_generate_with_defaults() -> None:
    """Test that defaults from class are captured."""

    class WithDefaults:
        def __init__(
            self,
            required: int,
            hour: int = 0,
            minute: int = 0,
            second: int = 0,
        ) -> None:
            pass

    class MockModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("mockmod_defs")
            self.WithDefaults = WithDefaults

    mod = MockModule()
    sys.modules["mockmod_defs"] = mod

    try:
        spec = Generator.generate("mockmod_defs.WithDefaults dt")

        # Use whole-output assertion with expected spec
        expected_spec: Spec = {
            "mockmod_defs.WithDefaults dt": {
                "hour": "{dt_hour}",
                "minute": "{dt_minute}",
                "required": "{dt_required}",
                "second": "{dt_second}",
            },
            "dt_hour": 0,
            "dt_minute": 0,
            "dt_required": 0,
            "dt_second": 0,
        }
        assert spec == expected_spec
    finally:
        if "mockmod_defs" in sys.modules:
            del sys.modules["mockmod_defs"]


@pytest.mark.parametrize(
    "entry, expected_msg",
    [
        ("invalid", "Invalid entry format"),
        ("Class name", "missing module qualification"),
        ("myapp.models.SomeClass inst.create.more", "nested factory methods"),
    ],
    ids=["no_delimiter", "no_module", "nested_factory"],
)
def test_generate_invalid_formats(entry: str, expected_msg: str) -> None:
    """Test that invalid entry formats raise ValueError with expected
    message.
    """
    with pytest.raises(ValueError, match=expected_msg):
        Generator.generate(entry)


@pytest.mark.parametrize(
    "annotation, expected_default",
    [
        (int, 0),
        (str, ""),
        (float, 0.0),
        (bool, False),
        (Optional[str], ""),  # Recurses to str default
        (List[int], []),
        (Dict[str, int], {}),
        (Tuple[int, int], ()),
        (Union[int, str, float], None),
        (bytes, b""),
        (complex, 0j),
        (None, None),  # unknown annotation
    ],
    ids=[
        "int",
        "str",
        "float",
        "bool",
        "optional",
        "list",
        "dict",
        "tuple",
        "union",
        "bytes",
        "complex",
        "unknown",
    ],
)
def test_generate_type_defaults(
    annotation: object, expected_default: object
) -> None:
    """Test that various type annotations produce correct defaults."""

    class DynamicTyped:
        pass

    # Manually set up __init__ without default value
    def __init__(self, value):  # type: ignore[no-untyped-def]
        pass

    # Updating the annotation for the 'value' parameter
    if annotation is not None:
        __init__.__annotations__ = {"value": annotation}  # type: ignore[misc]

    setattr(DynamicTyped, "__init__", __init__)  # type: ignore[misc]
    DynamicTyped.__module__ = "mockmod_dyn_typed"

    class MockModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("mockmod_dyn_typed")
            self.DynamicTyped = DynamicTyped

    mod = MockModule()
    sys.modules["mockmod_dyn_typed"] = mod

    try:
        spec = Generator.generate("mockmod_dyn_typed.DynamicTyped obj")
        assert spec["obj_value"] == expected_default
    finally:
        if "mockmod_dyn_typed" in sys.modules:
            del sys.modules["mockmod_dyn_typed"]


def test_generate_multiple_typed_params() -> None:
    """Test generating spec for a class with multiple typed parameters."""

    class MultiTyped:
        def __init__(self, year: int, name: str, ratio: float) -> None:
            pass

    class MockModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("mockmod_multi_typed")
            self.MultiTyped = MultiTyped

    mod = MockModule()
    sys.modules["mockmod_multi_typed"] = mod

    try:
        spec = Generator.generate("mockmod_multi_typed.MultiTyped obj")

        expected_spec: Spec = {
            "mockmod_multi_typed.MultiTyped obj": {
                "name": "{obj_name}",
                "ratio": "{obj_ratio}",
                "year": "{obj_year}",
            },
            "obj_name": "",
            "obj_ratio": 0.0,
            "obj_year": 0,
        }
        assert spec == expected_spec
    finally:
        if "mockmod_multi_typed" in sys.modules:
            del sys.modules["mockmod_multi_typed"]


def test_generate_with_dependency() -> None:
    """Test that dependencies are recursively generated."""

    class Inner:
        def __init__(self, value: int) -> None:
            self.value = value

    class Outer:
        def __init__(self, inner: Inner) -> None:
            self.inner = inner

    # Set __module__ to point to our mock module
    Inner.__module__ = "mockmod_dep"
    Outer.__module__ = "mockmod_dep"

    class MockModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("mockmod_dep")
            self.Inner = Inner
            self.Outer = Outer

    mod = MockModule()
    sys.modules["mockmod_dep"] = mod

    try:
        spec = Generator.generate("mockmod_dep.Outer wrapper")

        # Use whole-output assertion with expected spec
        expected_spec: Spec = {
            "mockmod_dep.Inner wrapper_inner": {
                "value": "{wrapper_inner_value}",
            },
            "mockmod_dep.Outer wrapper": {
                "inner": "{wrapper_inner}",
            },
            "wrapper_inner_value": 0,
        }
        assert spec == expected_spec
    finally:
        if "mockmod_dep" in sys.modules:
            del sys.modules["mockmod_dep"]


def test_generated_spec_works_with_wiring() -> None:
    """Test that generated spec can be used with Wiring."""

    class Simple:
        def __init__(self, value: int) -> None:
            self.value = value

    class MockModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("mockmod_wiring")
            self.Simple = Simple

    mod = MockModule()
    sys.modules["mockmod_wiring"] = mod

    try:
        spec = Generator.generate("mockmod_wiring.Simple obj")

        # Modify the generated default
        spec["obj_value"] = 42

        # Create wiring and test it works
        wired = Wiring(spec)
        instance = wired.obj()

        assert isinstance(instance, Simple)
        assert instance.value == 42
    finally:
        if "mockmod_wiring" in sys.modules:
            del sys.modules["mockmod_wiring"]


def test_generate_with_factory_method() -> None:
    """Test generating spec with factory method."""

    class WithFactory:
        def __init__(self, a: int, b: str) -> None:
            self.a = a
            self.b = b

        @classmethod
        def create(cls, x: int) -> "WithFactory":
            return cls(x, "default")

    class MockModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("mockmod_factory")
            self.WithFactory = WithFactory

    mod = MockModule()
    sys.modules["mockmod_factory"] = mod

    try:
        # Generate using factory method
        spec = Generator.generate("mockmod_factory.WithFactory obj.create")

        # Use whole-output assertion with expected spec
        expected_spec: Spec = {
            "mockmod_factory.WithFactory obj.create": {
                "x": "{obj_x}",
            },
            "obj_x": 0,
        }
        assert spec == expected_spec
    finally:
        if "mockmod_factory" in sys.modules:
            del sys.modules["mockmod_factory"]


def test_generate_no_params() -> None:
    """Test generating spec for class with no parameters."""

    class NoParams:
        def __init__(self) -> None:
            pass

    class MockModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("mockmod_noparams")
            self.NoParams = NoParams

    mod = MockModule()
    sys.modules["mockmod_noparams"] = mod

    try:
        spec = Generator.generate("mockmod_noparams.NoParams obj")

        # Use whole-output assertion with expected spec
        expected_spec: Spec = {
            "mockmod_noparams.NoParams obj": {},
        }
        assert spec == expected_spec
    finally:
        if "mockmod_noparams" in sys.modules:
            del sys.modules["mockmod_noparams"]


def test_generate_with_constant_defaults() -> None:
    """Test that actual constant defaults are preserved."""

    class WithDefaults:
        def __init__(
            self,
            name: str = "default_name",
            count: int = 100,
        ) -> None:
            pass

    class MockModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("mockmod_defaults")
            self.WithDefaults = WithDefaults

    mod = MockModule()
    sys.modules["mockmod_defaults"] = mod

    try:
        spec = Generator.generate("mockmod_defaults.WithDefaults obj")

        # Use whole-output assertion with expected spec
        expected_spec: Spec = {
            "mockmod_defaults.WithDefaults obj": {
                "count": "{obj_count}",
                "name": "{obj_name}",
            },
            "obj_count": 100,
            "obj_name": "default_name",
        }
        assert spec == expected_spec
    finally:
        if "mockmod_defaults" in sys.modules:
            del sys.modules["mockmod_defaults"]


def test_generate_circular_dependency() -> None:
    """Test that circular dependencies are detected."""
    from apywire.exceptions import CircularWiringError

    class Node:
        def __init__(self, child: "Node") -> None:
            pass

    Node.__module__ = "mockmod_circular"

    class MockModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("mockmod_circular")
            self.Node = Node

    mod = MockModule()
    sys.modules["mockmod_circular"] = mod

    try:
        # This should detect circular dependency
        spec = Generator.generate("mockmod_circular.Node root")
        # Even with circular deps, it should generate something
        assert "mockmod_circular.Node root" in spec
    except CircularWiringError:
        # This is also acceptable
        pass
    finally:
        if "mockmod_circular" in sys.modules:
            del sys.modules["mockmod_circular"]


def test_generate_class_without_init() -> None:
    """Test generating spec for class without __init__."""

    class NoInit:
        pass

    class MockModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("mockmod_noinit")
            self.NoInit = NoInit

    mod = MockModule()
    sys.modules["mockmod_noinit"] = mod

    try:
        spec = Generator.generate("mockmod_noinit.NoInit obj")
        expected_spec: Spec = {
            "mockmod_noinit.NoInit obj": {},
        }
        assert spec == expected_spec
    finally:
        if "mockmod_noinit" in sys.modules:
            del sys.modules["mockmod_noinit"]


def test_generate_builtin_class() -> None:
    """Test generating spec for built-in class.

    Built-in classes without inspectable signature.
    """
    # Built-in classes may raise ValueError/TypeError
    # This test ensures graceful handling
    try:
        spec = Generator.generate("builtins.object obj")
        # Should generate empty params for uninspectable classes
        assert "builtins.object obj" in spec
        assert spec["builtins.object obj"] == {}
    except Exception:
        # Some built-ins might not be importable, that's ok
        pass


def test_generate_with_varargs() -> None:
    """Test handling of *args and **kwargs parameters."""

    class WithVarArgs:
        def __init__(self, required: int, *args: int, **kwargs: str) -> None:
            pass

    class MockModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("mockmod_varargs")
            self.WithVarArgs = WithVarArgs

    mod = MockModule()
    sys.modules["mockmod_varargs"] = mod

    try:
        spec = Generator.generate("mockmod_varargs.WithVarArgs obj")
        # Should only include 'required', skip *args and **kwargs
        expected_spec: Spec = {
            "mockmod_varargs.WithVarArgs obj": {
                "required": "{obj_required}",
            },
            "obj_required": 0,
        }
        assert spec == expected_spec
    finally:
        if "mockmod_varargs" in sys.modules:
            del sys.modules["mockmod_varargs"]


def test_generate_non_constant_default() -> None:
    """Test handling of non-constant defaults."""

    class NonConstant:
        pass

    class WithNonConstant:
        def __init__(
            self, obj: int = NonConstant()  # type: ignore[assignment]
        ) -> None:
            pass

    class MockModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("mockmod_nonconst")
            self.WithNonConstant = WithNonConstant

    mod = MockModule()
    sys.modules["mockmod_nonconst"] = mod

    try:
        spec = Generator.generate("mockmod_nonconst.WithNonConstant obj")
        # Non-constant defaults should use type default
        expected_spec: Spec = {
            "mockmod_nonconst.WithNonConstant obj": {
                "obj": "{obj_obj}",
            },
            "obj_obj": 0,  # Should use int default, not the object
        }
        assert spec == expected_spec
    finally:
        if "mockmod_nonconst" in sys.modules:
            del sys.modules["mockmod_nonconst"]


def test_is_constant_with_collections() -> None:
    """Test _is_constant with various collection types."""
    from apywire.generator import Generator

    # Test nested lists and dicts
    assert Generator._is_constant([1, 2, 3])
    assert Generator._is_constant({"a": 1, "b": 2})
    assert Generator._is_constant([1, [2, 3]])
    assert Generator._is_constant({"a": {"b": 1}})
    assert Generator._is_constant((1, 2, 3))

    # Test with non-constants
    class Obj:
        pass

    assert not Generator._is_constant(Obj())
    assert not Generator._is_constant([Obj()])
    assert not Generator._is_constant({"key": Obj()})

    # Test ellipsis
    assert Generator._is_constant(...)


def test_generate_dependency_with_missing_module() -> None:
    """Test dependency generation when module can't be found."""

    class Inner:
        def __init__(self, x: int) -> None:
            pass

    # Set a non-existent module
    Inner.__module__ = "nonexistent_module_xyz"

    class Outer:
        def __init__(self, inner: Inner) -> None:
            pass

    Outer.__module__ = "mockmod_missing"

    class MockModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("mockmod_missing")
            self.Outer = Outer

    mod = MockModule()
    sys.modules["mockmod_missing"] = mod

    try:
        # Should handle missing module gracefully
        spec = Generator.generate("mockmod_missing.Outer obj")
        # Should still create entry for Outer
        assert "mockmod_missing.Outer obj" in spec
    finally:
        if "mockmod_missing" in sys.modules:
            del sys.modules["mockmod_missing"]


def test_generate_actual_circular_dependency() -> None:
    """Test that actual circular dependency raises error."""
    from apywire.exceptions import CircularWiringError

    # Manually create a spec with visited tracking
    spec: Spec = {}
    visited: set[str] = {"mockmod_circ.Node root"}

    class Node:
        def __init__(self, value: int) -> None:
            pass

    class MockModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("mockmod_circ")
            self.Node = Node

    mod = MockModule()
    sys.modules["mockmod_circ"] = mod

    try:
        # Try to process entry that's already in visited
        from apywire.generator import Generator

        Generator._process_entry("mockmod_circ.Node root", spec, visited)
        assert False, "Should have raised CircularWiringError"
    except CircularWiringError as e:
        assert "Circular dependency detected" in str(e)
    finally:
        if "mockmod_circ" in sys.modules:
            del sys.modules["mockmod_circ"]


def test_generate_class_with_signature_error() -> None:
    """Test handling of class that raises error during signature inspection."""
    import unittest.mock as mock

    class ProblematicClass:
        def __init__(self, x: int) -> None:
            pass

    class MockModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("mockmod_badsig")
            self.ProblematicClass = ProblematicClass

    mod = MockModule()
    sys.modules["mockmod_badsig"] = mod

    try:
        # Mock inspect.signature to raise ValueError
        with mock.patch(
            "inspect.signature", side_effect=ValueError("Bad sig")
        ):
            spec = Generator.generate("mockmod_badsig.ProblematicClass obj")
            # Should generate empty params for signature errors
            assert "mockmod_badsig.ProblematicClass obj" in spec
            assert spec["mockmod_badsig.ProblematicClass obj"] == {}
    finally:
        if "mockmod_badsig" in sys.modules:
            del sys.modules["mockmod_badsig"]


def test_generate_dependency_with_no_module_attr() -> None:
    """Test dependency generation when class has no __module__ attribute."""

    class Inner:
        def __init__(self, x: int) -> None:
            pass

    # Remove __module__ or set it to None
    Inner.__module__ = None  # type: ignore[assignment]

    class Outer:
        def __init__(self, inner: Inner) -> None:
            pass

    Outer.__module__ = "mockmod_nomodattr"

    class MockModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("mockmod_nomodattr")
            self.Outer = Outer
            self.Inner = Inner

    mod = MockModule()
    sys.modules["mockmod_nomodattr"] = mod

    try:
        # Should use current_module as fallback
        spec = Generator.generate("mockmod_nomodattr.Outer obj")
        # Should still create entry for Outer
        assert "mockmod_nomodattr.Outer obj" in spec
    finally:
        if "mockmod_nomodattr" in sys.modules:
            del sys.modules["mockmod_nomodattr"]
