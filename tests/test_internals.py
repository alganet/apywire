# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

import ast

import apywire
from apywire.wiring import _ResolvedValue, _WiredRef


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
    w = apywire.WiringCompiler({}, thread_safe=False)
    # Tuple containing WiredRef, string, and int should return ast.Tuple
    node = w._astify((_WiredRef("x"), "s", 1))
    assert isinstance(node, ast.Tuple)
    assert len(node.elts) == 3
    assert isinstance(node.elts[0], ast.Call)
    # The call should be `self.x()` so the callee is an Attribute
    assert isinstance(node.elts[0].func, ast.Attribute)
    assert isinstance(node.elts[1], ast.Constant)
    assert isinstance(node.elts[2], ast.Constant)

    # For an arbitrary object, ast.Constant should be returned
    class Dummy:
        pass

    d = Dummy()
    # We're intentionally testing the fallback behavior with an invalid type
    from typing import cast

    const_node = w._astify(cast(_ResolvedValue, d))
    assert isinstance(const_node, ast.Constant)
    # ast.Constant.value is typed as a union of constant types, but we're
    # testing the fallback behavior, so we cast to object for the check
    assert cast(object, const_node.value) is d


def test_topological_sort_orders_dependencies_first() -> None:
    w = apywire.Wiring({}, thread_safe=False)
    # c depends on b, b depends on a; result must list each dep before its
    # dependent and be deterministic.
    deps = {"c": {"b"}, "b": {"a"}, "a": set()}
    order = w._topological_sort(deps)
    assert order == ["a", "b", "c"]
    # External (out-of-set) references are ignored for ordering.
    assert w._topological_sort({"a": {"external"}}) == ["a"]


def test_topological_sort_deterministic_for_independent_nodes() -> None:
    w = apywire.Wiring({}, thread_safe=False)
    # Multiple roots and a shared dependent. Zero-degree roots are emitted in
    # insertion order (a, b, c); d becomes ready once b is processed and is
    # appended behind the already-queued c. The exact sequence is pinned so a
    # regression that reorders output (and would change compiled-output bytes)
    # fails here rather than silently passing.
    deps = {"a": set(), "b": set(), "d": {"a", "b"}, "c": set()}
    assert w._topological_sort(deps) == ["a", "b", "c", "d"]
    # Reordering the insertion order reorders the output correspondingly.
    reordered = {"c": set(), "b": set(), "a": set(), "d": {"a", "b"}}
    assert w._topological_sort(reordered) == ["c", "b", "a", "d"]


def test_topological_sort_raises_on_cycle() -> None:
    import pytest

    from apywire.exceptions import CircularWiringError

    w = apywire.Wiring({}, thread_safe=False)
    with pytest.raises(CircularWiringError):
        w._topological_sort({"a": {"b"}, "b": {"a"}})
