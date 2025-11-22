# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

"""A package to wire up objects."""

from .exceptions import (
    CircularWiringError,
    LockUnavailableError,
    UnknownPlaceholderError,
    WiringError,
)
from .wiring import (
    Accessor,
    AioAccessor,
    Spec,
    SpecEntry,
    Wiring,
)

__all__ = [
    "Spec",
    "SpecEntry",
    "Wiring",
    "WiringError",
    "UnknownPlaceholderError",
    "CircularWiringError",
    "LockUnavailableError",
    "Accessor",
    "AioAccessor",
]
