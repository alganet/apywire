# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

"""Tests for emitting the source spec into compiled containers."""

import datetime
from typing import Protocol, cast

import pytest

from apywire import Spec, Wiring, WiringCompiler, merge_specs


class _Compiled(Protocol):
    """Structural type for the compiled container under test."""

    def birthday(self) -> object: ...


def _spec() -> Spec:
    """A spec exercising constants, refs and nested containers."""
    return {
        "year": 1990,
        "datetime.date birthday": {
            "year": "{year}",
            "month": 12,
            "day": 13,
        },
    }


def _exec(code: str) -> dict[str, object]:
    """Execute compiled source and return its module namespace."""
    execd: dict[str, object] = {}
    exec(code, execd)
    return execd


def test_compile_without_emit_spec_omits_spec_literal() -> None:
    """The default output is unchanged: no spec is emitted."""
    code = WiringCompiler(_spec()).compile()

    assert "spec = {" not in code
    assert "spec" not in _exec(code)


def test_compile_emit_spec_roundtrips_original_spec() -> None:
    """The emitted spec is the source spec, not the parsed form."""
    spec = _spec()
    code = WiringCompiler(spec).compile(emit_spec=True)

    assert _exec(code)["spec"] == spec


def test_compile_emit_spec_writes_one_entry_per_line() -> None:
    """A compiled defaults module is committed, so it must diff readably.

    Unparsed as one expression, changing a single default would rewrite
    one enormous line.
    """
    code = WiringCompiler(_spec()).compile(emit_spec=True)

    assert "spec = {\n" in code
    assert "    'year': 1990,\n" in code
    assert "    'datetime.date birthday': {" in code


def test_compile_emit_spec_preserves_placeholder_strings() -> None:
    """Placeholders survive verbatim, so the spec can be re-wired."""
    code = WiringCompiler(_spec()).compile(emit_spec=True)
    emitted = cast(Spec, _exec(code)["spec"])

    assert emitted["datetime.date birthday"] == {
        "year": "{year}",
        "month": 12,
        "day": 13,
    }
    assert Wiring(emitted).birthday() == datetime.date(1990, 12, 13)


def test_compile_emit_spec_preserves_positional_int_keys() -> None:
    """Positional keys stay ints, not strings."""
    spec: Spec = {"datetime.date d.fromordinal": {0: 730000}}
    code = WiringCompiler(spec).compile(emit_spec=True)

    assert _exec(code)["spec"] == {"datetime.date d.fromordinal": {0: 730000}}


def test_compile_emit_spec_handles_nested_containers() -> None:
    """Every literal shape a spec can hold round-trips."""
    spec: Spec = {
        "text": "a",
        "raw": b"b",
        "flag": True,
        "count": 3,
        "ratio": 1.5,
        "imaginary": complex(1, 2),
        "nothing": None,
        "anything": ...,
        "items": [1, ["nested"], ("tup",), {"k": "v"}],
    }
    code = WiringCompiler(spec).compile(emit_spec=True)

    assert _exec(code)["spec"] == spec


def test_compile_emit_spec_with_aio_and_thread_safe_is_valid() -> None:
    """The spec is emitted alongside the aio/thread-safe container."""
    code = WiringCompiler(_spec()).compile(
        aio=True, thread_safe=True, emit_spec=True
    )
    execd = _exec(code)

    assert execd["spec"] == _spec()
    compiled = cast(_Compiled, execd["compiled"])
    assert compiled.birthday() == datetime.date(1990, 12, 13)


def test_compile_emit_spec_non_literal_value_raises_value_error() -> None:
    """A spec value with no source representation cannot be emitted."""
    spec: Spec = {"thing": {"bad": {1, 2}}}  # type: ignore[dict-item]

    compiler = WiringCompiler(spec)
    assert compiler.compile()  # compiles fine without emitting

    with pytest.raises(ValueError, match="is not a literal"):
        compiler.compile(emit_spec=True)


def test_compile_emit_spec_module_named_spec_raises_value_error() -> None:
    """A wired module named 'spec' would be shadowed by the emission."""
    compiler = WiringCompiler({"spec.Thing x": {}})
    assert compiler.compile()  # compiles fine without emitting

    with pytest.raises(ValueError, match="would be shadowed"):
        compiler.compile(emit_spec=True)


def test_compile_emit_spec_output_is_mergeable() -> None:
    """The whole point: compiled defaults can be overlaid and re-wired.

    This is the shape a consumer needs -- compile a defaults file for
    speed, then let a user's config extend it at runtime.
    """
    code = WiringCompiler(_spec()).compile(emit_spec=True)
    defaults = cast(Spec, _exec(code)["spec"])

    merged = merge_specs(defaults, {"year": 2001})

    assert Wiring(merged).birthday() == datetime.date(2001, 12, 13)
