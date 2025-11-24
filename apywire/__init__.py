# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

"""A package to wire up objects."""

from .compiler import WiringCompiler
from .exceptions import (
    CircularWiringError,
    LockUnavailableError,
    UnknownPlaceholderError,
    WiringError,
)
from .runtime import Accessor, AioAccessor, Spec, SpecEntry, WiringRuntime
from .wiring import WiringBase

Wiring = WiringRuntime

__all__ = [
    "Spec",
    "SpecEntry",
    "Wiring",
    "WiringRuntime",
    "WiringCompiler",
    "WiringBase",
    "WiringError",
    "UnknownPlaceholderError",
    "CircularWiringError",
    "LockUnavailableError",
    "Accessor",
    "AioAccessor",
]
