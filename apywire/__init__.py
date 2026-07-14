# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

"""A package to wire up objects."""

from .compiler import WiringCompiler
from .exceptions import (
    CircularWiringError,
    LockUnavailableError,
    MergeError,
    UnknownPlaceholderError,
    WiringError,
)
from .generator import Generator
from .merge import merge_specs
from .runtime import (
    Accessor,
    AioAccessor,
    CompiledAio,
    Spec,
    SpecEntry,
    WiringRuntime,
)
from .threads import ThreadSafeMixin
from .wiring import WiringBase

Wiring = WiringRuntime

__all__ = [
    "Spec",
    "SpecEntry",
    "ThreadSafeMixin",
    "Wiring",
    "WiringRuntime",
    "WiringCompiler",
    "WiringBase",
    "WiringError",
    "UnknownPlaceholderError",
    "CircularWiringError",
    "LockUnavailableError",
    "MergeError",
    "Accessor",
    "AioAccessor",
    "CompiledAio",
    "Generator",
    "merge_specs",
]
