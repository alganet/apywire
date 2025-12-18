# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

"""Tests for placeholder expansion in constants."""

import sys
from types import ModuleType

import pytest

import apywire


@pytest.mark.parametrize(
    "spec, expected_key, expected_val",
    [
        ({"a": "foo", "b": "{a} bar"}, "b", "foo bar"),
        ({"port": 5432, "url": "localhost:{port}"}, "url", "localhost:5432"),
        ({"number": 42, "message": "{number}"}, "message", "42"),
    ],
    ids=["basic", "int_port", "int_ref"],
)
def test_constant_value_expansion(
    spec: apywire.Spec, expected_key: str, expected_val: str
) -> None:
    """Test basic placeholder expansion in constants with various value
    types.
    """
    wired = apywire.Wiring(spec, thread_safe=False)
    assert wired._values[expected_key] == expected_val


def test_nested_constant_dependencies() -> None:
    """Test nested constant dependencies with correct ordering."""
    spec: apywire.Spec = {
        "a": "1",
        "b": "{a}2",
        "c": "{b}3",
    }
    wired = apywire.Wiring(spec, thread_safe=False)
    assert wired._values["a"] == "1"
    assert wired._values["b"] == "12"
    assert wired._values["c"] == "123"


def test_auto_promoted_constant_with_wired_object() -> None:
    """Test auto-promotion of constant referencing wired object."""
    spec: apywire.Spec = {
        "datetime.datetime now": {"year": 2025, "month": 1, "day": 1},
        "message": "Time: {now}",
    }
    wired = apywire.Wiring(spec, thread_safe=False)

    # message should be an accessor, not in _values
    assert "message" not in wired._values
    assert "message" in wired._parsed

    # Calling the accessor should return formatted string
    msg = wired.message()
    assert isinstance(msg, str)
    assert "2025-01-01" in msg


def test_mixed_constant_and_wired_refs() -> None:
    """Test constant with both constant and wired object references."""
    spec: apywire.Spec = {
        "host": "localhost",
        "datetime.datetime now": {"year": 2025, "month": 6, "day": 15},
        "status": "Server {host} at {now}",
    }
    wired = apywire.Wiring(spec, thread_safe=False)

    # host should be a constant
    assert wired._values["host"] == "localhost"

    # status should be auto-promoted (has wired ref)
    assert "status" not in wired._values
    assert "status" in wired._parsed

    # Calling the accessor
    status = wired.status()
    assert isinstance(status, str)
    assert "localhost" in status
    assert "2025" in status


def test_circular_dependency_in_constants() -> None:
    """Test that circular dependencies in constants raise error at init."""
    spec: apywire.Spec = {
        "a": "{b}",
        "b": "{a}",
    }

    with pytest.raises(apywire.CircularWiringError) as exc_info:
        apywire.Wiring(spec, thread_safe=False)

    assert "Circular wiring dependency detected" in str(exc_info.value)


def test_circular_with_wired_objects() -> None:
    """Test circular dependency with wired objects (existing behavior)."""
    # Create mock module for testing
    mod = ModuleType("test_module")

    class MyClass:
        def __init__(self, dep: object) -> None:
            self.dep = dep

    mod.MyClass = MyClass  # type: ignore[attr-defined]
    sys.modules["test_module"] = mod

    try:
        spec: apywire.Spec = {
            "test_module.MyClass a": {"dep": "{b}"},
            "test_module.MyClass b": {"dep": "{a}"},
        }
        # Should raise at init time now (no lazy access errors)
        with pytest.raises(apywire.CircularWiringError):
            apywire.Wiring(spec, thread_safe=False)
    finally:
        del sys.modules["test_module"]


@pytest.mark.parametrize(
    "spec, expected_key, expected_val",
    [
        (
            {"base": "/app", "config": {"path": "{base}/config.yaml"}},
            "config",
            {"path": "/app/config.yaml"},
        ),
        (
            {
                "base": "http://api",
                "endpoints": ["{base}/users", "{base}/posts"],
            },
            "endpoints",
            ["http://api/users", "http://api/posts"],
        ),
        (
            {"base": "test", "data": ("{base}", "{base}")},
            "data",
            ("test", "test"),
        ),
    ],
    ids=["dict", "list", "tuple"],
)
def test_constant_collection_expansion(
    spec: apywire.Spec, expected_key: str, expected_val: object
) -> None:
    """Test placeholder expansion in nested data structures and collections."""
    wired = apywire.Wiring(spec, thread_safe=False)
    assert wired._values[expected_key] == expected_val


def test_string_representation_of_wired_object() -> None:
    """Test that wired objects are converted using str()."""
    # Create mock module
    mod = ModuleType("test_module")

    class MyClass:
        def __str__(self) -> str:
            return "custom_str"

    mod.MyClass = MyClass  # type: ignore[attr-defined]
    sys.modules["test_module"] = mod

    try:
        spec: apywire.Spec = {
            "test_module.MyClass obj": {},
            "message": "Object: {obj}",
        }
        wired = apywire.Wiring(spec, thread_safe=False)

        result = wired.message()
        assert result == "Object: custom_str"
    finally:
        del sys.modules["test_module"]


def test_unknown_constant_placeholder() -> None:
    """Test that unknown constant placeholder raises error."""
    spec: apywire.Spec = {
        "a": "{nonexistent}",
    }

    with pytest.raises(apywire.UnknownPlaceholderError) as exc_info:
        apywire.Wiring(spec, thread_safe=False)

    assert "nonexistent" in str(exc_info.value)


def test_with_thread_safe_mode() -> None:
    """Test that constant expansion works in thread-safe mode."""
    spec: apywire.Spec = {
        "host": "localhost",
        "port": 5432,
        "db_url": "postgresql://{host}:{port}/mydb",
    }
    wired = apywire.Wiring(spec, thread_safe=True)

    assert wired._values["db_url"] == "postgresql://localhost:5432/mydb"


def test_no_placeholders() -> None:
    """Test that constants without placeholders work normally."""
    spec: apywire.Spec = {
        "a": "plain string",
        "b": 42,
        "c": ["list", "items"],
    }
    wired = apywire.Wiring(spec, thread_safe=False)

    assert wired._values["a"] == "plain string"
    assert wired._values["b"] == 42
    assert wired._values["c"] == ["list", "items"]


def test_compilation_with_placeholders() -> None:
    """Test that compilation works with placeholder expansion."""
    spec: apywire.Spec = {
        "host": "localhost",
        "port": 5432,
        "db_url": "postgresql://{host}:{port}/mydb",
        "datetime.datetime now": {"year": 2025, "month": 1, "day": 1},
        "message": "DB at {db_url}, time: {now}",
    }

    # Compile the spec
    code = apywire.WiringCompiler(spec).compile()

    # Verify constant expansion in compiled code
    assert "db_url" in code
    assert "postgresql://localhost:5432/mydb" in code

    # Auto-promoted constants are NOT compiled
    # (they require runtime interpolation with wired objects)
    assert "def message" not in code

    # Execute compiled code
    namespace: dict[str, object] = {}
    exec(code, namespace)

    # Verify compiled code works (auto-promoted constants are skipped)
    # Dynamic access not fully type-checked by mypy for exec'd code


def test_interpolate_placeholders_unknown_placeholder() -> None:
    """Test that _interpolate_placeholders raises on unknown placeholder."""

    from apywire import Spec, Wiring
    from apywire.exceptions import UnknownPlaceholderError

    spec: Spec = {"base": "value"}
    wired = Wiring(spec, thread_safe=False)

    # Call _interpolate_placeholders with unknown placeholder
    with pytest.raises(UnknownPlaceholderError, match="Unknown placeholder"):
        wired._interpolate_placeholders(
            "Test {unknown}", {"base": "value"}, "test"
        )


def test_transitive_promotion_of_constants() -> None:
    """Test transitive promotion of constants with wired refs."""
    import sys
    from types import ModuleType

    from apywire import Spec, Wiring

    class MyClass:
        def __init__(self) -> None:
            pass

    mod = ModuleType("test_transitive")
    mod.MyClass = MyClass  # type: ignore[attr-defined]
    sys.modules["test_transitive"] = mod

    try:
        # c depends on b, b depends on a, a depends on wired obj
        spec: Spec = {
            "test_transitive.MyClass obj": {},
            "a": "Object: {obj}",
            "b": "B: {a}",
            "c": "C: {b}",
        }
        wired = Wiring(spec, thread_safe=False)

        # All three should be promoted (not in _values)
        assert "a" not in wired._values
        assert "b" not in wired._values
        assert "c" not in wired._values

        # All should be in _parsed as auto-promoted
        assert "a" in wired._parsed
        assert "b" in wired._parsed
        assert "c" in wired._parsed

    finally:
        del sys.modules["test_transitive"]
