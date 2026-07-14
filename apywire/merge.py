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
they are replaced wholesale rather than recursed into, and an append
marker deeper than that is an error rather than data.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import NamedTuple, TypeAlias, TypeVar, cast

from apywire.constants import APPEND_PREFIX, SPEC_KEY_DELIMITER
from apywire.exceptions import MergeError
from apywire.wiring import (
    Spec,
    SpecEntry,
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


class _Entry(NamedTuple):
    """An indexed spec entry, keyed by its exposed name."""

    key: str
    value: _SpecValue
    ident: _Ident | None  # None for constants


def merge_specs(base: Spec, *overlays: Spec) -> Spec:
    """Overlay specs onto a base spec, left to right.

    Same-name entries override, new entries are appended, and a
    ``+``-prefixed key appends to the base's list value for that key.
    Neither the inputs nor their nested values are mutated, and the
    result shares no mutable container with them.

    Args:
        base: The spec to overlay onto.
        *overlays: Specs applied in order; later ones win. With none,
            the base is validated and returned as a copy.

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
    index: dict[str, _Entry] = {}
    for spec in (base, *overlays):
        index = _apply(index, spec)
    return {entry.key: cast(_SpecTop, entry.value) for entry in index.values()}


def _apply(index: dict[str, _Entry], spec: Spec) -> dict[str, _Entry]:
    """Apply one spec over an indexed spec, returning a new index.

    The base is folded through this too, over an empty index: a base
    entry is simply one with nothing to inherit from, and a base ``+``
    key is one with nothing to append to.
    """
    plain, appends = _split_appends(spec, None)

    merged = dict(index)
    seen: dict[str, str] = {}
    for key, value in plain.items():
        name, ident = _parse_key(key)
        _reject_duplicate(seen, name, key)
        merged[name] = _merge_entry(name, merged.get(name), key, value, ident)

    for name, value in appends.items():
        existing = merged.get(name)
        if existing is None:
            raise MergeError(_no_target(name, None, merged))
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
        if ident is None:
            return _Entry(name, _prepare(value, None), None)
        return _Entry(key, _wired_data(None, value, name), ident)

    if ident is None:
        # A bare-name key addresses the entry of that name: against a
        # wired entry it means its arguments, so a config need not repeat
        # (and stay in sync with) a class path the library owns.
        if existing.ident is not None:
            return _Entry(
                existing.key,
                _wired_data(existing.value, value, name),
                existing.ident,
            )
        return _Entry(name, _prepare(value, None), None)

    if ident == existing.ident:
        return _Entry(
            existing.key,
            _wired_data(existing.value, value, name),
            ident,
        )

    # A different type path means the base's arguments belong to another
    # class; inheriting them would pass kwargs the new class may not
    # accept, so replace the entry wholesale (keeping the base's slot).
    return _Entry(key, _wired_data(None, value, name), ident)


def _wired_data(
    base_value: _SpecValue | None,
    overlay_value: _SpecValue,
    name: str,
) -> _SpecValue:
    """Merge a wired entry's constructor arguments.

    A dict is keyword arguments and merges key by key; a list is
    positional arguments and replaces wholesale. A ``None`` base means
    "nothing to inherit" -- a new entry, or one whose type path changed.
    """
    if isinstance(overlay_value, dict):
        base_data: SpecEntry = (
            base_value if isinstance(base_value, dict) else {}
        )
        return _merge_entry_data(base_data, overlay_value, name)
    if isinstance(overlay_value, list):
        return _prepare(overlay_value, name)

    # Demoting the entry to a constant would silently drop its class.
    raise MergeError(
        f"cannot give wired entry '{name}' a "
        f"{type(overlay_value).__name__} as its arguments: expected a "
        f"table (keyword arguments) or a list (positional arguments)"
    )


def _merge_entry_data(
    base_data: SpecEntry,
    overlay_data: SpecEntry,
    context: str,
) -> SpecEntry:
    """Merge two entries' argument dicts, applying any ``+`` markers."""
    plain, appends = _split_appends(overlay_data, context)

    merged: SpecEntry = dict(base_data)
    merged.update({k: _prepare(v, context) for k, v in plain.items()})

    for name, value in appends.items():
        if name not in base_data:
            raise MergeError(_no_target(name, context, base_data))
        # Assigning an existing key keeps it in the base's position.
        merged[name] = _append_list(name, base_data[name], value, context)
    return merged


def _prepare(value: _SpecValue, context: str | None) -> _SpecValue:
    """Copy a value, rejecting append markers below where they mean something.

    Markers are interpreted at the top level of a spec and of a wired
    entry's arguments. Deeper down a value is opaque data, so a ``+`` key
    there would be handed to a constructor verbatim; reject it instead of
    silently passing it through. Containers are rebuilt so the merged
    spec shares no mutable state with the specs it came from.
    """
    if isinstance(value, dict):
        for key in value:
            if isinstance(key, str) and key.startswith(APPEND_PREFIX):
                raise MergeError(
                    f"invalid key '{key}'{_where(context)}: the "
                    f"'{APPEND_PREFIX}' append marker is only supported "
                    f"at the top level of a spec or of a wired entry"
                )
        return {k: _prepare(v, context) for k, v in value.items()}
    if isinstance(value, list):
        return [_prepare(v, context) for v in value]
    if isinstance(value, tuple):
        return tuple(_prepare(v, context) for v in value)
    return value


def _split_appends(
    mapping: Mapping[_K, _SpecValue],
    context: str | None,
) -> tuple[dict[_K, _SpecValue], dict[str, _SpecValue]]:
    """Split a mapping into plain keys and stripped ``+`` append keys.

    Args:
        mapping: A spec (``context`` is None) or an entry's arguments.
        context: The entry name, for error messages; None at spec level.

    Returns:
        The plain keys, and the append keys with the marker stripped.

    Raises:
        MergeError: On a marker that cannot mean anything: an unknown
            one, or ``+`` on a wired key, on a positional key, or
            alongside its own plain key.
    """
    plain: dict[_K, _SpecValue] = {}
    appends: dict[str, _SpecValue] = {}

    for key, value in mapping.items():
        if not isinstance(key, str) or not key.startswith(APPEND_PREFIX):
            if isinstance(key, str):
                _reject_unknown_marker(key, context)
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
                f"conflicting keys '{name}' and '{key}'{_where(context)}"
            )
        appends[name] = value

    return plain, appends


def _reject_unknown_marker(key: str, context: str | None) -> None:
    """Reject a key that looks like a marker but is not one.

    ``-key`` and ``^key`` are the natural guesses for "remove" and
    "prepend" once ``+key`` is known. Neither exists, and a spec key or
    an argument name never legitimately starts with punctuation, so
    passing one through as data would silently misconfigure a container.
    """
    first = key[:1]
    if first and not (first.isalnum() or first == "_"):
        raise MergeError(
            f"unknown merge marker '{first}' in key "
            f"'{key}'{_where(context)}: only '{APPEND_PREFIX}' (append) "
            f"is supported"
        )


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
    prepared = _prepare(overlay_value, context)
    return [*base_value, *cast("list[_SpecValue]", prepared)]


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


def _no_target(
    name: str,
    context: str | None,
    known: Iterable[str | int],
) -> str:
    """Message for a ``+`` key with no matching base key."""
    names = ", ".join(sorted(str(k) for k in known)) or "none"
    return (
        f"cannot append to '{name}'{_where(context)}: the base has no "
        f"such key (known keys: {names})"
    )


def _where(context: str | None) -> str:
    """Render the entry context for an error message, if any."""
    return f" in entry '{context}'" if context is not None else ""
