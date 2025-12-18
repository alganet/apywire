# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

from types import ModuleType
from typing import Protocol

import pytest

import apywire
from apywire.exceptions import CircularWiringError


class M(ModuleType):
    def __init__(self) -> None:
        super().__init__("m")


class HasB(Protocol):
    b: object


class HasA(Protocol):
    a: object


class A:
    def __init__(self, b: HasB) -> None:
        self.b = b


class B:
    def __init__(self, a: HasA) -> None:
        self.a = a


def test_detect_cycle_between_constant_and_wired() -> None:
    # constant 'c' references 'w' and wired 'w' references 'c' -> cycle
    spec: apywire.Spec = {
        "c": "{w}",
        "tests.test_graph_detection.A w": {"b": "{c}"},
    }

    with pytest.raises(CircularWiringError):
        apywire.Wiring(spec)


def test_detect_cycle_mixed_wired_constants() -> None:
    # Round-trip cycle across multiple entries
    spec: apywire.Spec = {
        "a": "{b}",
        "tests.test_graph_detection.A b": {"b": "{c}"},
        "c": "{a}",
    }

    with pytest.raises(CircularWiringError):
        apywire.Wiring(spec)


def test_no_false_positive_for_external_placeholders() -> None:
    # Placeholder references an external name (not in spec) should not
    # cause a cycle detection.
    spec: apywire.Spec = {
        "a": "{b}",
        "tests.test_graph_detection.A c": {"b": "foo"},
    }

    # Should not raise a circular-wiring error; resolving constants will
    # surface a meaningful UnknownPlaceholderError for missing constant
    with pytest.raises(apywire.UnknownPlaceholderError):
        apywire.Wiring(spec)
