# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

import ast

import apywire
from apywire.wiring import _WiredRef


def test_resolve_string_and_tuple_returning_expected_types() -> None:
    w = apywire.Wiring({}, thread_safe=False)
    # Non-placeholder string returns as-is
    assert w._resolve("plain") == "plain"

    # Tuple elements are resolved recursively, including placeholder refs
    t = ("a", "{b}", 1)
    resolved = w._resolve(t)
    assert isinstance(resolved, tuple)
    assert resolved[0] == "a"
    assert isinstance(resolved[1], _WiredRef)
    assert resolved[1].name == "b"
    assert resolved[2] == 1


def test_resolve_runtime_tuple_resolves_wiredrefs_to_values() -> None:
    w = apywire.Wiring({}, thread_safe=False)
    # Put a value in _values so getattr doesn't need to import
    w._values["foo"] = 42

    resolved_tuple = (_WiredRef("foo"), 5)
    runtime_value = w._resolve_runtime(resolved_tuple)
    assert isinstance(runtime_value, tuple)
    assert isinstance(runtime_value[0], int) and runtime_value[0] == 42
    assert isinstance(runtime_value[1], int) and runtime_value[1] == 5


def test_astify_tuple_and_fallback_to_constant() -> None:
    w = apywire.Wiring({}, thread_safe=False)
    # Tuple containing WiredRef, string, and int should return ast.Tuple
    node = w._astify((_WiredRef("x"), "s", 1))
    assert isinstance(node, ast.Tuple)
    assert len(node.elts) == 3
    assert isinstance(node.elts[0], ast.Attribute)
    assert isinstance(node.elts[1], ast.Constant)
    assert isinstance(node.elts[2], ast.Constant)

    # For an arbitrary object, ast.Constant should be returned
    class Dummy:
        pass

    d = Dummy()
    # We're intentionally testing the fallback behavior with an invalid type
    from typing import cast

    from apywire.wiring import _ResolvedValue

    const_node = w._astify(cast(_ResolvedValue, d))
    assert isinstance(const_node, ast.Constant)
    # ast.Constant.value is typed as a union of constant types, but we're
    # testing the fallback behavior, so we cast to object for the check
    assert cast(object, const_node.value) is d
