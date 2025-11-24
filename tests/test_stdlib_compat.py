# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

import datetime
import pathlib
from typing import cast

import apywire


def test_stdlib_int_list_args() -> None:
    """Test instantiating int with positional arguments from a list."""
    spec: apywire.Spec = {"builtins.int myInt": [10]}
    wired = apywire.Wiring(spec)
    assert wired.myInt() == 10


def test_stdlib_int_dict_numeric_args() -> None:
    """Test instantiating int with positional arguments from numeric keys."""
    spec: apywire.Spec = {"builtins.int myInt": {0: 42}}
    wired = apywire.Wiring(spec)
    assert wired.myInt() == 42


def test_stdlib_complex_mixed_args() -> None:
    """Test instantiating complex with mixed positional and keyword
    arguments.
    """
    # complex(real, imag)
    # real as positional (0), imag as keyword
    spec: apywire.Spec = {"builtins.complex myComplex": {0: 1.5, "imag": 2.5}}
    wired = apywire.Wiring(spec)
    c = cast(complex, wired.myComplex())
    assert c.real == 1.5
    assert c.imag == 2.5


def test_stdlib_path_args() -> None:
    """Test instantiating pathlib.Path with positional arguments."""
    spec: apywire.Spec = {"pathlib.Path myPath": ["/tmp", "foo"]}
    wired = apywire.Wiring(spec)
    p = wired.myPath()
    assert isinstance(p, pathlib.Path)
    assert str(p) == "/tmp/foo"


def test_stdlib_date_args() -> None:
    """Test instantiating datetime.date with positional arguments."""
    spec: apywire.Spec = {"datetime.date myDate": [2023, 10, 27]}
    wired = apywire.Wiring(spec)
    d = wired.myDate()
    assert d == datetime.date(2023, 10, 27)


def test_compile_list_args() -> None:
    """Test compilation of list arguments."""
    spec: apywire.Spec = {"builtins.int myInt": [99]}
    code = apywire.WiringCompiler(spec).compile()

    execd: dict[str, object] = {}
    exec(code, execd)
    compiled = execd["compiled"]

    # We can't easily type check the dynamic compiled object without a
    # Protocol, but we can check the attribute.
    assert cast(int, getattr(compiled, "myInt")()) == 99


def test_compile_mixed_args() -> None:
    """Test compilation of mixed numeric/string keys."""
    spec: apywire.Spec = {"builtins.complex myComplex": {0: 1.0, "imag": 2.0}}
    code = apywire.WiringCompiler(spec).compile()

    execd: dict[str, object] = {}
    exec(code, execd)
    compiled = execd["compiled"]

    c = cast(complex, getattr(compiled, "myComplex")())
    assert c == complex(1.0, 2.0)
