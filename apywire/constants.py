# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

"""Shared constants for the apywire package.

This module centralizes magic strings and values used throughout the codebase
to improve maintainability and reduce duplication.
"""

SPEC_KEY_DELIMITER = " "  # Separates module.Class from name in spec keys

PLACEHOLDER_START = "{"  # Start marker for placeholder references
PLACEHOLDER_END = "}"  # End marker for placeholder references

# Regex pattern for placeholders like {name}: captures name, no nested braces
PLACEHOLDER_PATTERN = r"\{([^{}]+)\}"

SYNTHETIC_CONST = "__sconst__"  # Synthetic module for promoted constants

CACHE_ATTR_PREFIX = "_"  # Prefix for cache attributes (_name)

COMPILED_VAR_PREFIX = "__val_"  # Prefix for temp variables in compiled code
COMPILED_ARG_PREFIX = (
    "__arg_"  # Prefix for argument variables in compiled code
)
