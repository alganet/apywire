# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

"""A package to wire up objects."""

from .wiring import (
    Accessor,
    AioAccessor,
    CircularWiringError,
    Spec,
    SpecEntry,
    UnknownPlaceholderError,
    Wiring,
    WiringError,
)

__all__ = [
    "Spec",
    "SpecEntry",
    "Wiring",
    "WiringError",
    "UnknownPlaceholderError",
    "CircularWiringError",
    "Accessor",
    "AioAccessor",
]
