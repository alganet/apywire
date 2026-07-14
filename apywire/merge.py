# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

"""Overlay one wiring spec on top of another.

``merge_specs`` folds overlay specs onto a base spec and returns a plain
:data:`~apywire.Spec`, so the result is consumed by ``Wiring`` and
``WiringCompiler`` unchanged -- merging adds no wiring semantics.

Entries are matched by their *exposed name* (the token after the last
space in a spec key), not by the raw key string, so a base
``"pkg.Registry registry"`` and an overlay ``"mine.Registry registry"``
are the same entry. A ``+``-prefixed key appends to the base's list value
for that key; the marker is stripped here and never reaches a container.

The merge is exactly two levels deep -- spec, then entry. Values inside
an entry are constructor arguments, not configuration namespaces, so
they are replaced wholesale rather than recursed into.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import NamedTuple, TypeAlias, TypeVar, cast

from apywire.constants import APPEND_PREFIX, SPEC_KEY_DELIMITER
from apywire.exceptions import MergeError
from apywire.wiring import (
    Spec,
    SpecParser,
    _ConstantValue,
    _SpecMapping,
    _SpecValue,
)

# The value type of a Spec entry, as opposed to a value nested inside one.
_SpecTop: TypeAlias = _SpecMapping | _ConstantValue

# A wired entry's type path: (module, class, factory method).
_Ident: TypeAlias = tuple[str, str, str | None]

# Spec keys are strings; entry keys are strings or positional ints.
_K = TypeVar("_K", bound=str | int)

_EntryData: TypeAlias = dict[str | int, _SpecValue]


class _Entry(NamedTuple):
    """An indexed spec entry, keyed by its exposed name."""

    key: str
    value: _SpecValue
    ident: _Ident | None  # None for constants


def merge_specs(base: Spec, *overlays: Spec) -> Spec:
    """Overlay specs onto a base spec, left to right.

    Same-name entries override, new entries are appended, and a
    ``+``-prefixed key appends to the base's list value for that key.
    Inputs are never mutated.

    Args:
        base: The spec to overlay onto.
        *overlays: Specs applied in order; later ones win. With none,
            the base is validated and returned as a fresh dict.

    Returns:
        The merged spec, in base order, with overlay-only entries last.

    Raises:
        MergeError: If the specs cannot be merged.
        ValueError: If a spec key is malformed.

    Example:
        >>> base = {"pkg.Registry registry": {"repos": ["{a}"]}}
        >>> overlay = {"registry": {"+repos": ["{b}"]}}
        >>> merge_specs(base, overlay)
        {'pkg.Registry registry': {'repos': ['{a}', '{b}']}}
    """
    index = _index(base)
    for overlay in overlays:
        index = _apply(index, overlay)
    return {entry.key: cast(_SpecTop, entry.value) for entry in index.values()}


def _index(base: Spec) -> dict[str, _Entry]:
    """Index a base spec by exposed name, validating it on the way.

    A ``+`` key in a base spec has nothing to append to, so the base is
    routed through the same entry merger with an empty base -- which is
    what makes a stray marker an error instead of a leak.
    """
    plain, appends = _split_appends(base, None)
    if appends:
        raise MergeError(_no_target(next(iter(appends)), None))

    index: dict[str, _Entry] = {}
    seen: dict[str, str] = {}
    for key, value in plain.items():
        name, ident = _parse_key(key)
        _reject_duplicate(seen, name, key)
        index[name] = _Entry(key, _merged_data(None, value, name), ident)
    return index


def _apply(index: dict[str, _Entry], overlay: Spec) -> dict[str, _Entry]:
    """Apply one overlay to an indexed spec, returning a new index."""
    plain, appends = _split_appends(overlay, None)

    merged = dict(index)
    seen: dict[str, str] = {}
    for key, value in plain.items():
        name, ident = _parse_key(key)
        _reject_duplicate(seen, name, key)
        merged[name] = _merge_entry(name, merged.get(name), key, value, ident)

    for name, value in appends.items():
        existing = merged.get(name)
        if existing is None:
            raise MergeError(_no_target(name, None))
        merged[name] = _Entry(
            existing.key,
            _append_list(name, existing.value, value, None),
            existing.ident,
        )
    return merged


def _merge_entry(
    name: str,
    existing: _Entry | None,
    key: str,
    value: _SpecValue,
    ident: _Ident | None,
) -> _Entry:
    """Merge one overlay entry onto the base entry of the same name."""
    if existing is None:
        return _Entry(key, _merged_data(None, value, name), ident)

    if ident is None:
        # A bare-name key extends the wired entry it names, so a config
        # need not repeat (and stay in sync with) the class path.
        if isinstance(value, dict) and existing.ident is not None:
            return _Entry(
                existing.key,
                _merged_data(existing.value, value, name),
                existing.ident,
            )
        return _Entry(name, _merged_data(None, value, name), None)

    if ident == existing.ident:
        return _Entry(
            existing.key,
            _merged_data(existing.value, value, name),
            ident,
        )

    # A different type path means the base's arguments belong to another
    # class; inheriting them would pass kwargs the new class may not
    # accept, so replace the entry wholesale (keeping the base's slot).
    return _Entry(key, _merged_data(None, value, name), ident)


def _merged_data(
    base_value: _SpecValue | None,
    overlay_value: _SpecValue,
    name: str,
) -> _SpecValue:
    """Merge an entry's data, one level deep.

    A non-dict overlay value replaces the base wholesale. A ``None``
    base means "nothing to inherit" -- used both when indexing a base
    spec and when an overlay replaces an entry outright.
    """
    if not isinstance(overlay_value, dict):
        return overlay_value
    base_data: _EntryData = base_value if isinstance(base_value, dict) else {}
    return _merge_entry_data(base_data, overlay_value, name)


def _merge_entry_data(
    base_data: _EntryData,
    overlay_data: _EntryData,
    context: str,
) -> _EntryData:
    """Merge two entries' data dicts, applying any ``+`` markers."""
    plain, appends = _split_appends(overlay_data, context)

    merged: _EntryData = dict(base_data)
    for key, value in plain.items():
        merged[key] = value

    for name, value in appends.items():
        if name not in base_data:
            raise MergeError(_no_target(name, context))
        # Assigning an existing key keeps it in the base's position.
        merged[name] = _append_list(name, base_data[name], value, context)
    return merged


def _split_appends(
    mapping: Mapping[_K, _SpecValue],
    context: str | None,
) -> tuple[dict[_K, _SpecValue], dict[str, _SpecValue]]:
    """Split a mapping into plain keys and stripped ``+`` append keys.

    Args:
        mapping: A spec (``context`` is None) or an entry's data.
        context: The entry name, for error messages; None at spec level.

    Returns:
        The plain keys, and the append keys with the marker stripped.

    Raises:
        MergeError: On a marker that cannot mean anything: on a wired
            key, on a positional key, or alongside its own plain key.
    """
    plain: dict[_K, _SpecValue] = {}
    appends: dict[str, _SpecValue] = {}

    for key, value in mapping.items():
        if not isinstance(key, str) or not key.startswith(APPEND_PREFIX):
            plain[key] = value
            continue

        name = key[len(APPEND_PREFIX) :]
        if context is None:
            if SPEC_KEY_DELIMITER in name:
                raise MergeError(
                    f"invalid key '{key}': the '{APPEND_PREFIX}' append "
                    f"marker cannot be used on a wired entry key"
                )
        elif name.isdigit():
            raise MergeError(
                f"invalid key '{key}' in entry '{context}': the "
                f"'{APPEND_PREFIX}' append marker cannot be used on "
                f"positional keys"
            )
        if name in mapping:
            raise MergeError(
                f"conflicting keys '{name}' and '{key}'" f"{_where(context)}"
            )
        appends[name] = value

    return plain, appends


def _append_list(
    name: str,
    base_value: _SpecValue,
    overlay_value: _SpecValue,
    context: str | None,
) -> list[_SpecValue]:
    """Append an overlay's list to the base's list for one key."""
    where = _where(context)
    if not isinstance(base_value, list):
        raise MergeError(
            f"cannot append to '{name}'{where}: the base value is a "
            f"{type(base_value).__name__}, not a list"
        )
    if not isinstance(overlay_value, list):
        raise MergeError(
            f"invalid value for '{APPEND_PREFIX}{name}'{where}: expected "
            f"a list, got {type(overlay_value).__name__}"
        )
    return [*base_value, *overlay_value]


def _parse_key(key: str) -> tuple[str, _Ident | None]:
    """Split a spec key into its exposed name and its type path."""
    parsed = SpecParser._parse_request_string(key)
    if parsed is None:
        return key, None
    module_name, class_name, name, factory_method = parsed
    return name, (module_name, class_name, factory_method)


def _reject_duplicate(seen: dict[str, str], name: str, key: str) -> None:
    """Reject two keys in one spec that expose the same name."""
    previous = seen.get(name)
    if previous is not None:
        raise MergeError(
            f"duplicate exposed name '{name}': keys '{previous}' and "
            f"'{key}'"
        )
    seen[name] = key


def _no_target(name: str, context: str | None) -> str:
    """Message for a ``+`` key with no matching base key."""
    return (
        f"cannot append to '{name}'{_where(context)}: the base has no "
        f"such key"
    )


def _where(context: str | None) -> str:
    """Render the entry context for an error message, if any."""
    return f" in entry '{context}'" if context else ""
