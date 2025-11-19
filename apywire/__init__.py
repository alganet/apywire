# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

"""A package to wire up objects."""

from .wiring import (
    Blueprint,
    InstanceData,
    Spec,
    Wired,
    compile,
    wire,
)

__all__ = [
    "Blueprint",
    "InstanceData",
    "Spec",
    "Wired",
    "compile",
    "wire",
]
