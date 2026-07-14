# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

"""Shared constants for the apywire package.

This module centralizes magic strings and values used throughout the codebase
to improve maintainability and reduce duplication.
"""

import re

SPEC_KEY_DELIMITER = " "  # Separates module.Class from name in spec keys

APPEND_PREFIX = "+"  # Marks a spec key that appends to a base list value

PLACEHOLDER_START = "{"  # Start marker for placeholder references
PLACEHOLDER_END = "}"  # End marker for placeholder references

# Regex pattern for placeholders like {name}: captures name, no nested braces
PLACEHOLDER_PATTERN = r"\{([^{}]+)\}"
# Compiled version for better performance
PLACEHOLDER_REGEX = re.compile(PLACEHOLDER_PATTERN)

SYNTHETIC_CONST = "__sconst__"  # Synthetic module for promoted constants

SPEC_EMIT_NAME = "spec"  # Module-level name for a compiled spec literal

COMPILED_CLASS_NAME = "Compiled"  # Class name in generated code

CACHE_ATTR_PREFIX = "_"  # Prefix for cache attributes (_name)

# Thread-safety defaults: max retries and per-retry sleep when falling back
# to the global lock in thread_safe mode.
DEFAULT_MAX_LOCK_ATTEMPTS = 10
DEFAULT_LOCK_RETRY_SLEEP = 0.01
