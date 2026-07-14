# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

"""Tests for overlaying wiring specs with merge_specs."""

import sys
from types import ModuleType
from typing import Protocol

import pytest

from apywire import MergeError, Wiring, WiringCompiler, merge_specs
from apywire.formats import ini_to_spec, json_to_spec, toml_to_spec
from apywire.wiring import Spec

REGISTRY_KEY = "merge_module.Registry registry"


class Registry:
    """A registry over a list of repos -- the shape this feature serves."""

    def __init__(self, repos: list[str], cache: str) -> None:
        self.repos = repos
        self.cache = cache


class MockModule(ModuleType):
    """A module exposing Registry, for the wiring tests."""

    def __init__(self) -> None:
        super().__init__("merge_module")
        self.Registry = Registry


class _Compiled(Protocol):
    """Structural type for the compiled container under test."""

    def registry(self) -> object: ...


def _base() -> Spec:
    """A base spec shaped like a real one: a wired entry over a list."""
    return {
        "alpha": "A",
        "beta": "B",
        REGISTRY_KEY: {"repos": ["{alpha}"], "cache": "/tmp"},
    }


# --- Top-level merging ------------------------------------------------


def test_merge_new_constant_is_added() -> None:
    """An overlay-only constant is added to the merged spec."""
    merged = merge_specs({"a": 1}, {"b": 2})
    assert merged == {"a": 1, "b": 2}


def test_merge_existing_constant_overlay_value_wins() -> None:
    """A same-name constant is replaced by the overlay's value."""
    merged = merge_specs({"a": 1}, {"a": 2})
    assert merged == {"a": 2}


def test_merge_new_wired_entry_is_appended() -> None:
    """An overlay-only wired entry is appended after the base's."""
    base: Spec = {"datetime.date d": {"year": 2000}}
    overlay: Spec = {"argparse.Namespace n": {"x": 1}}
    merged = merge_specs(base, overlay)
    assert list(merged) == ["datetime.date d", "argparse.Namespace n"]


def test_merge_same_key_deep_merges_entry_keys() -> None:
    """A same-type-path entry merges key by key."""
    merged = merge_specs(
        {"argparse.Namespace n": {"x": 1, "y": 2}},
        {"argparse.Namespace n": {"y": 3}},
    )
    assert merged == {"argparse.Namespace n": {"x": 1, "y": 3}}


def test_merge_bare_name_dict_extends_wired_entry() -> None:
    """A bare-name dict extends the wired entry it names."""
    merged = merge_specs(_base(), {"registry": {"cache": "/var"}})
    assert merged[REGISTRY_KEY] == {"repos": ["{alpha}"], "cache": "/var"}
    assert REGISTRY_KEY in merged
    assert "registry" not in merged


def test_merge_bare_name_scalar_replaces_wired_entry() -> None:
    """A bare-name scalar turns a wired entry into a constant."""
    merged = merge_specs(_base(), {"registry": 5})
    assert merged["registry"] == 5
    assert REGISTRY_KEY not in merged


def test_merge_constant_replaced_by_wired_entry() -> None:
    """A wired overlay entry replaces a same-name base constant."""
    merged = merge_specs({"n": 1}, {"argparse.Namespace n": {"x": 1}})
    assert merged == {"argparse.Namespace n": {"x": 1}}


def test_merge_constant_dict_is_replaced_not_merged() -> None:
    """Two constants with dict values replace, they do not merge."""
    merged = merge_specs({"n": {"x": 1}}, {"n": {"y": 2}})
    assert merged == {"n": {"y": 2}}


def test_merge_different_type_path_replaces_entry() -> None:
    """A changed type path replaces the entry rather than merging it.

    The naive ``{**base, **overlay}`` leaves *both* key strings in the
    dict; only one of them then wins inside Wiring. Pin that it does not
    happen here.
    """
    merged = merge_specs(
        {"argparse.Namespace n": {"x": 1}, "z": 9},
        {"datetime.date n": {"year": 2000}},
    )
    assert list(merged) == ["datetime.date n", "z"]
    assert merged["datetime.date n"] == {"year": 2000}


def test_merge_wired_entry_data_list_is_replaced() -> None:
    """Positional (list) entry data is replaced, never merged."""
    merged = merge_specs(
        {"argparse.Namespace n": {"x": 1}},
        {"argparse.Namespace n": [1, 2]},
    )
    assert merged == {"argparse.Namespace n": [1, 2]}


def test_merge_nested_dict_value_is_replaced_not_recursed() -> None:
    """The merge is two levels deep: nested values replace wholesale."""
    merged = merge_specs(
        {"argparse.Namespace n": {"opts": {"a": 1, "b": 2}}},
        {"argparse.Namespace n": {"opts": {"b": 3}}},
    )
    assert merged == {"argparse.Namespace n": {"opts": {"b": 3}}}


def test_merge_int_positional_keys_are_overridden_by_index() -> None:
    """Positional keys override by index, not by position."""
    merged = merge_specs(
        {"argparse.Namespace n": {0: "a", 1: "b"}},
        {"argparse.Namespace n": {1: "c"}},
    )
    assert merged == {"argparse.Namespace n": {0: "a", 1: "c"}}


def test_merge_preserves_base_key_order() -> None:
    """Overridden entries keep the base's slot; new ones go last."""
    base: Spec = {"a": 1, "b": 2, "c": 3}
    merged = merge_specs(base, {"b": 20, "d": 4})
    assert list(merged) == ["a", "b", "c", "d"]


def test_merge_multiple_overlays_apply_left_to_right() -> None:
    """Overlays fold left to right; the last one wins."""
    merged = merge_specs({"a": 1}, {"a": 2, "b": 1}, {"a": 3})
    assert merged == {"a": 3, "b": 1}


def test_merge_no_overlays_returns_normalized_copy() -> None:
    """With no overlays the base is validated and copied."""
    base = _base()
    merged = merge_specs(base)
    assert merged == base
    assert merged is not base


def test_merge_does_not_mutate_inputs() -> None:
    """Merging never mutates the base or the overlay."""
    base = _base()
    overlay: Spec = {"registry": {"+repos": ["{beta}"]}}
    merge_specs(base, overlay)
    assert base == _base()
    assert overlay == {"registry": {"+repos": ["{beta}"]}}


# --- The append marker ------------------------------------------------


def test_merge_append_marker_extends_base_list() -> None:
    """A '+' key appends to the base's list for that key."""
    merged = merge_specs(_base(), {"registry": {"+repos": ["{beta}"]}})
    assert merged[REGISTRY_KEY] == {
        "repos": ["{alpha}", "{beta}"],
        "cache": "/tmp",
    }


def test_merge_append_marker_extends_top_level_constant_list() -> None:
    """A '+' key works on a top-level constant list too."""
    merged = merge_specs({"items": [1, 2]}, {"+items": [3]})
    assert merged == {"items": [1, 2, 3]}


def test_merge_append_marker_is_stripped_from_output() -> None:
    """No '+' key ever survives into the merged spec."""
    merged = merge_specs(_base(), {"registry": {"+repos": ["{beta}"]}})
    for key, value in merged.items():
        assert not key.startswith("+")
        if isinstance(value, dict):
            for inner in value:
                assert not str(inner).startswith("+")


def test_merge_append_keeps_the_base_key_position() -> None:
    """An appended key stays where the base put it."""
    merged = merge_specs(
        {"argparse.Namespace n": {"repos": [1], "cache": "/tmp"}},
        {"argparse.Namespace n": {"+repos": [2]}},
    )
    entry = merged["argparse.Namespace n"]
    assert isinstance(entry, dict)
    assert list(entry) == ["repos", "cache"]


def test_merge_int_key_is_never_treated_as_append() -> None:
    """Positional int keys are plain keys, never append markers."""
    merged = merge_specs(
        {"argparse.Namespace n": {0: "a"}},
        {"argparse.Namespace n": {0: "b"}},
    )
    assert merged == {"argparse.Namespace n": {0: "b"}}


# --- Errors -----------------------------------------------------------


def test_merge_duplicate_exposed_name_in_base_raises() -> None:
    """Two base keys exposing one name are ambiguous."""
    base: Spec = {
        "argparse.Namespace n": {"x": 1},
        "datetime.date n": {"year": 2000},
    }
    with pytest.raises(MergeError, match="duplicate exposed name 'n'"):
        merge_specs(base)


def test_merge_duplicate_exposed_name_in_overlay_raises() -> None:
    """Two overlay keys exposing one name are ambiguous."""
    overlay: Spec = {
        "argparse.Namespace n": {"x": 1},
        "datetime.date n": {"year": 2000},
    }
    with pytest.raises(MergeError, match="duplicate exposed name 'n'"):
        merge_specs({"a": 1}, overlay)


def test_merge_append_marker_on_wired_key_raises() -> None:
    """A '+' marker on a wired key has no meaning."""
    with pytest.raises(MergeError, match="cannot be used on a wired"):
        merge_specs({"a": 1}, {"+argparse.Namespace n": {"x": 1}})


def test_merge_append_marker_on_positional_key_raises() -> None:
    """A '+' marker on a positional key has no meaning."""
    with pytest.raises(MergeError, match="on positional keys"):
        merge_specs(
            {"argparse.Namespace n": {0: [1]}},
            {"argparse.Namespace n": {"+0": [2]}},
        )


def test_merge_append_and_plain_key_conflict_raises() -> None:
    """An entry cannot both set and append to the same key."""
    with pytest.raises(
        MergeError, match="conflicting keys 'repos' and '\\+repos'"
    ):
        merge_specs(
            _base(),
            {REGISTRY_KEY: {"repos": [1], "+repos": [2]}},
        )


def test_merge_top_level_append_and_plain_key_conflict_raises() -> None:
    """A spec cannot both set and append to the same constant."""
    with pytest.raises(MergeError, match="conflicting keys 'items'"):
        merge_specs({"items": [1]}, {"items": [2], "+items": [3]})


def test_merge_append_missing_base_key_raises() -> None:
    """Appending to a key the base does not have is an error."""
    with pytest.raises(
        MergeError, match="cannot append to 'nope' in entry 'registry'"
    ):
        merge_specs(_base(), {"registry": {"+nope": [1]}})


def test_merge_top_level_append_missing_base_key_raises() -> None:
    """Appending to a constant the base does not have is an error."""
    with pytest.raises(MergeError, match="cannot append to 'nope'"):
        merge_specs({"a": 1}, {"+nope": [1]})


def test_merge_append_after_type_path_change_raises() -> None:
    """A replaced entry brings no base list to append to."""
    with pytest.raises(
        MergeError, match="cannot append to 'repos' in entry 'registry'"
    ):
        merge_specs(_base(), {"datetime.date registry": {"+repos": [1]}})


def test_merge_append_in_base_spec_raises() -> None:
    """A '+' key in the base has nothing to append to."""
    with pytest.raises(MergeError, match="cannot append to 'items'"):
        merge_specs({"+items": [1]})


def test_merge_append_in_base_entry_raises() -> None:
    """A '+' key inside a base entry has nothing to append to."""
    with pytest.raises(
        MergeError, match="cannot append to 'repos' in entry 'n'"
    ):
        merge_specs({"argparse.Namespace n": {"+repos": [1]}})


def test_merge_append_to_non_list_base_raises() -> None:
    """Appending to a non-list base value is an error."""
    with pytest.raises(MergeError, match="the base value is a str"):
        merge_specs(_base(), {"registry": {"+cache": ["/var"]}})


def test_merge_append_non_list_value_raises() -> None:
    """A '+' key's value must be a list."""
    with pytest.raises(MergeError, match="expected a list, got str"):
        merge_specs(_base(), {"registry": {"+repos": "{beta}"}})


def test_merge_malformed_key_raises_value_error() -> None:
    """A malformed spec key fails as it does in Wiring."""
    with pytest.raises(ValueError, match="missing module qualification"):
        merge_specs({"Namespace n": {"x": 1}})


# --- Formats ----------------------------------------------------------


def test_merge_is_format_neutral() -> None:
    """The same overlay merges identically from TOML, JSON and INI.

    merge_specs works on the Spec dict every format adapter produces, so
    it needs no format-specific code.
    """
    toml = '["merge_module.Registry registry"]\n"+repos" = ["{beta}"]\n'
    json = '{"merge_module.Registry registry": {"+repos": ["{beta}"]}}'
    ini = '[merge_module.Registry registry]\n+repos = ["{beta}"]\n'

    from_toml = merge_specs(_base(), toml_to_spec(toml))
    from_json = merge_specs(_base(), json_to_spec(json))
    from_ini = merge_specs(_base(), ini_to_spec(ini))

    assert from_toml == from_json == from_ini
    assert from_toml[REGISTRY_KEY] == {
        "repos": ["{alpha}", "{beta}"],
        "cache": "/tmp",
    }


# --- Equivalence: the merged spec wires, at runtime and compiled ------


def test_merge_result_wires_at_runtime() -> None:
    """A merged spec is an ordinary spec: it wires unchanged."""
    sys.modules["merge_module"] = MockModule()
    try:
        merged = merge_specs(_base(), {"registry": {"+repos": ["{beta}"]}})
        registry = Wiring(merged).registry()
        assert isinstance(registry, Registry)
        assert registry.repos == ["A", "B"]
        assert registry.cache == "/tmp"
    finally:
        del sys.modules["merge_module"]


def test_merge_result_compiles_to_equivalent_container() -> None:
    """The compiled container behaves like the runtime one."""
    sys.modules["merge_module"] = MockModule()
    try:
        merged = merge_specs(_base(), {"registry": {"+repos": ["{beta}"]}})

        code = WiringCompiler(merged).compile()
        execd: dict[str, _Compiled] = {}
        exec(code, execd)

        compiled = execd["compiled"].registry()
        runtime = Wiring(merged).registry()
        assert isinstance(compiled, Registry)
        assert isinstance(runtime, Registry)
        assert compiled.repos == runtime.repos == ["A", "B"]
        assert compiled.cache == runtime.cache == "/tmp"
    finally:
        del sys.modules["merge_module"]


def test_merge_result_compiles_thread_safe_and_aio() -> None:
    """A merged spec compiles in the aio/thread-safe modes too."""
    sys.modules["merge_module"] = MockModule()
    try:
        merged = merge_specs(_base(), {"registry": {"+repos": ["{beta}"]}})

        code = WiringCompiler(merged).compile(aio=True, thread_safe=True)
        execd: dict[str, _Compiled] = {}
        exec(code, execd)

        registry = execd["compiled"].registry()
        assert isinstance(registry, Registry)
        assert registry.repos == ["A", "B"]
    finally:
        del sys.modules["merge_module"]
