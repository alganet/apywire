# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

"""Shared constants for the apywire package.

This module centralizes magic strings and values used throughout the codebase
to improve maintainability and reduce duplication.
"""

# Spec parsing constants
SPEC_KEY_DELIMITER = " "
"""Delimiter used to separate module.Class from name in spec keys."""

# Placeholder constants
PLACEHOLDER_START = "{"
"""Start marker for placeholder references in spec values."""

PLACEHOLDER_END = "}"
"""End marker for placeholder references in spec values."""

# Placeholder regex pattern (compiled for efficiency)
PLACEHOLDER_PATTERN = r"\{([^{}]+)\}"
"""Regex pattern for matching placeholders like {name}.

Matches placeholder syntax with the following rules:
- Starts with { and ends with }
- Captures the placeholder name (group 1)
- Does not allow nested braces in the name
- Example: "{host}" matches with name="host"
"""

SYNTHETIC_CONST = "__sconst__"
"""Synthetic module name used to represent promoted constants."""

# Cache attribute constants
CACHE_ATTR_PREFIX = "_"
"""Prefix for cache attributes on compiled/runtime instances."""

# Compiled code generation constants
COMPILED_VAR_PREFIX = "__val_"
"""Prefix for temporary variables in compiled code."""

COMPILED_ARG_PREFIX = "__arg_"
"""Prefix for argument variables in compiled code."""
