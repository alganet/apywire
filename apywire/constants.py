# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

"""Shared constants for the apywire package.

This module centralizes magic strings and values used throughout the codebase
to improve maintainability and reduce duplication.
"""

import re

SPEC_KEY_DELIMITER = " "  # Separates module.Class from name in spec keys

PLACEHOLDER_START = "{"  # Start marker for placeholder references
PLACEHOLDER_END = "}"  # End marker for placeholder references

# Regex pattern for placeholders like {name}: captures name, no nested braces
PLACEHOLDER_PATTERN = r"\{([^{}]+)\}"
# Compiled version for better performance
PLACEHOLDER_REGEX = re.compile(PLACEHOLDER_PATTERN)

SYNTHETIC_CONST = "__sconst__"  # Synthetic module for promoted constants

CACHE_ATTR_PREFIX = "_"  # Prefix for cache attributes (_name)
