# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

"""Exception classes for apywire.

This module contains all exception types used throughout the apywire
library, including exceptions for wiring errors and thread-safety
internal exceptions.
"""


class WiringError(AttributeError):
    """Raised when the wiring system cannot instantiate an attribute.

    This wraps the underlying exception to provide context on which
    attribute failed to instantiate, while preserving the original
    exception as the cause.
    """


class UnknownPlaceholderError(WiringError):
    """Raised by `_resolve_runtime` when a placeholder name is not
    found in either constants (`_values`) or parsed spec entries
    (`_parsed`).
    """


class CircularWiringError(WiringError):
    """Raised when a circular wiring dependency is detected.

    This class is a `WiringError` subtype for simpler programmatic
    handling of wiring-specific failures.
    """


class PartialConstructionAccessError(WiringError):
    """Raised when attempting to access or call an object that is still in
    partial construction (placeholder inserted but not yet finalized).

    This error indicates the wiring is in a transient state and the user
    attempted to use the placeholder before it was bound to the final
    instance.
    """


class PartialConstructionError(WiringError):
    """Raised when partial construction cannot be completed successfully.

    Examples include factories that bypass `__new__` and return a different
    instance than the skeleton allocated by the wiring system.
    """


class LockUnavailableError(RuntimeError):
    """Exception raised when a per-attribute lock cannot be acquired in
    optimistic (non-blocking) mode and the code must fall back to a global
    lock.

    This exception is used internally by the thread-safety system but is also
    referenced in compiled code, so it is part of the public API.
    """


class FormatError(ValueError):
    """Raised when parsing or serializing a spec in a specific format fails.

    This wraps the underlying parsing exception to provide context about
    the format being used and a user-friendly error message.
    """

    def __init__(self, fmt: str, message: str) -> None:
        self.format = fmt
        super().__init__(f"{fmt.upper()} format error: {message}")
