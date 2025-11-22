# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

import ast
import threading

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

    from apywire.wiring import _ResolvedValue

    const_node = w._astify(cast(_ResolvedValue, d))
    assert isinstance(const_node, ast.Constant)
    # ast.Constant.value is typed as a union of constant types, but we're
    # testing the fallback behavior, so we cast to object for the check
    assert cast(object, const_node.value) is d


def test_get_resolving_stack_returns_per_thread_or_shared() -> None:
    # Non-thread-safe: stacks should be the same across calls and threads
    w1 = apywire.Wiring({}, thread_safe=False)
    s1 = w1._get_resolving_stack()
    s2 = w1._get_resolving_stack()
    assert s1 is s2

    stack_id_in_thread = None

    def capture_shared_stack_id() -> None:
        nonlocal stack_id_in_thread
        stack_id_in_thread = id(w1._get_resolving_stack())

    t = threading.Thread(target=capture_shared_stack_id)
    t.start()
    t.join()
    assert stack_id_in_thread == id(s1)

    # Thread-safe: each thread should get a distinct resolving stack
    w2 = apywire.Wiring({}, thread_safe=True)
    st_main = w2._get_resolving_stack()
    st_main2 = w2._get_resolving_stack()
    assert st_main is st_main2

    main_stack_id = id(st_main)
    stack_id_other_thread = None

    def capture_local_stack_id() -> None:
        nonlocal stack_id_other_thread
        stack_id_other_thread = id(w2._get_resolving_stack())

    t2 = threading.Thread(target=capture_local_stack_id)
    t2.start()
    t2.join()
    assert stack_id_other_thread != main_stack_id
