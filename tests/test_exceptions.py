# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

"""Tests for exception classes and helpers."""

from __future__ import annotations

import re

import apywire
from apywire import CircularWiringError
from apywire.exceptions import FormatError


def test_circular_wiring_error_from_unprocessed_detects_cycle() -> None:
    """The helper should return an error message that includes a cycle path."""

    deps = {
        "a": {"b"},
        "b": {"a"},
        "c": set(),
    }

    err = CircularWiringError.from_unprocessed(deps, ["a", "b"])

    msg = str(err)
    assert "Circular dependency detected" in msg
    assert "a" in msg and "b" in msg
    assert "cycle:" in msg
    # cycle should be rendered as a -> b -> a or b -> a -> b
    assert re.search(r"a\s*->\s*b\s*->\s*a|b\s*->\s*a\s*->\s*b", msg)


def test_circular_wiring_error_from_unprocessed_no_cycle_path() -> None:
    """If no cycle path can be extracted, message should list the nodes."""

    deps: dict[str, set[str]] = {
        "a": set(),
        "b": set(),
    }

    err = CircularWiringError.from_unprocessed(deps, ["a", "b"])
    msg = str(err)

    assert msg == "Circular dependency detected: a, b"


def test_format_error_includes_format_and_message() -> None:
    fe = FormatError("json", "invalid token")
    assert fe.format == "json"
    assert str(fe) == "JSON format error: invalid token"


def test_exception_hierarchy() -> None:
    """Sanity checks for exception subclassing."""
    assert issubclass(apywire.UnknownPlaceholderError, apywire.WiringError)
    assert issubclass(apywire.CircularWiringError, apywire.WiringError)
    assert issubclass(apywire.LockUnavailableError, RuntimeError)
