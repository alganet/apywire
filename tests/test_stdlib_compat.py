# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

import datetime
import pathlib
from typing import Callable, cast

import pytest

import apywire


@pytest.mark.parametrize(
    "class_path, args, expected",
    [
        ("builtins.int", [10], 10),
        ("builtins.int", {0: 42}, 42),
        ("builtins.complex", {0: 1.5, "imag": 2.5}, complex(1.5, 2.5)),
        ("pathlib.Path", ["/tmp", "foo"], pathlib.Path("/tmp/foo")),
        ("datetime.date", [2023, 10, 27], datetime.date(2023, 10, 27)),
    ],
    ids=["int_list", "int_dict", "complex_mixed", "path", "date"],
)
def test_stdlib_instantiation(
    class_path: str, args: object, expected: object
) -> None:
    """Test instantiating various stdlib classes with different argument
    formats.
    """
    spec = {f"{class_path} obj": args}
    wired = apywire.Wiring(spec)  # type: ignore[arg-type]
    assert wired.obj() == expected


@pytest.mark.parametrize(
    "class_path, args, expected",
    [
        ("builtins.int", [99], 99),
        ("builtins.complex", {0: 1.0, "imag": 2.0}, complex(1.0, 2.0)),
    ],
    ids=["int", "complex"],
)
def test_compile_stdlib_instantiation(
    class_path: str, args: object, expected: object
) -> None:
    """Test compilation of various stdlib classes with different argument
    formats.
    """
    spec = {f"{class_path} obj": args}
    code = apywire.WiringCompiler(spec).compile()  # type: ignore[arg-type]

    execd: dict[str, object] = {}
    exec(code, execd)
    compiled = execd["compiled"]

    assert cast(Callable[[], object], getattr(compiled, "obj"))() == expected
