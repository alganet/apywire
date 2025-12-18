# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

import sys
from types import ModuleType
from typing import Protocol, cast, runtime_checkable

import apywire


@runtime_checkable
class CompPartialModule(Protocol):
    """Protocol for dynamically created comp_partial module."""

    A: type
    B: type


@runtime_checkable
class ClassWithDep(Protocol):
    """Protocol for classes with a dep attribute."""

    dep: object


@runtime_checkable
class CompiledModule(Protocol):
    """Protocol for compiled wiring module."""

    def a(self) -> ClassWithDep: ...
    def b(self) -> ClassWithDep: ...


def test_compile_partial_factory_identity_preserved_sync() -> None:
    """Compiled non-async accessors preserve identity for
    factory-based cycles.
    """

    class CompPartialModuleImpl(ModuleType):
        A: type
        B: type

    mod = CompPartialModuleImpl("comp_partial")

    class A:
        def __init__(self, dep: object | None = None) -> None:
            self.dep = dep

        @classmethod
        def create(cls, dep: object | None = None) -> "A":
            return cls(dep)

    class B:
        def __init__(self, dep: object | None = None) -> None:
            self.dep = dep

        @classmethod
        def create(cls, dep: object | None = None) -> "B":
            return cls(dep)

    mod.A = A
    mod.B = B
    sys.modules["comp_partial"] = mod

    try:
        spec: apywire.Spec = {
            "comp_partial.A a.create": {"dep": "{b}"},
            "comp_partial.B b.create": {"dep": "{a}"},
        }
        compiler = apywire.WiringCompiler(spec, allow_partial=True)
        code = compiler.compile(aio=False)

        execd: dict[str, object] = {}
        exec(code, execd)
        compiled = cast(CompiledModule, execd["compiled"])

        a = compiled.a()
        b = compiled.b()

        assert a.dep is b
        assert b.dep is a
    finally:
        del sys.modules["comp_partial"]
