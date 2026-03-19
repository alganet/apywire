# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

"""Tests for spec format adapters."""

from typing import Callable

import pytest

from apywire import Wiring
from apywire.formats import (
    ini_to_spec,
    json_to_spec,
    spec_to_ini,
    spec_to_json,
    spec_to_toml,
    toml_to_spec,
)
from apywire.wiring import Spec


@pytest.mark.parametrize(
    "to_format, from_format",
    [
        (spec_to_json, json_to_spec),
        (spec_to_toml, toml_to_spec),
        (spec_to_ini, ini_to_spec),
    ],
    ids=["json", "toml", "ini"],
)
class TestFormatRoundtrips:
    """Set of tests for format roundtrip compatibility."""

    def test_roundtrip_simple_spec(
        self,
        to_format: "Callable[[Spec], str]",
        from_format: "Callable[[str], Spec]",
    ) -> None:
        """Test roundtrip with simple spec."""
        spec: Spec = {
            "datetime.datetime now": {"year": "{now_year}"},
            "now_year": 2025,
        }
        formatted = to_format(spec)
        result = from_format(formatted)
        assert result == spec

    def test_roundtrip_with_constants(
        self,
        to_format: "Callable[[Spec], str]",
        from_format: "Callable[[str], Spec]",
    ) -> None:
        """Test roundtrip with various constant types."""
        spec: Spec = {
            "datetime.datetime now": {},
            "str_const": "hello",
            "int_const": 42,
            "float_const": 3.14,
            "bool_const": True,
        }
        # JSON and our INI adapter support None (serialized as "" in INI)
        # TOML does not support None/null.
        if to_format is not spec_to_toml:
            spec["none_const"] = None

        formatted = to_format(spec)
        result = from_format(formatted)
        assert result == spec

    def test_roundtrip_with_nested_data(
        self,
        to_format: "Callable[[Spec], str]",
        from_format: "Callable[[str], Spec]",
    ) -> None:
        """Test roundtrip with nested lists and dicts."""
        spec: Spec = {
            "mymod.MyClass obj": {
                "items": [1, 2, 3],
            },
        }
        obj_spec = spec["mymod.MyClass obj"]
        if isinstance(obj_spec, dict):
            obj_spec["config"] = {"key": "value"}

        formatted = to_format(spec)
        result = from_format(formatted)
        assert result == spec

    def test_roundtrip_empty_spec(
        self,
        to_format: "Callable[[Spec], str]",
        from_format: "Callable[[str], Spec]",
    ) -> None:
        """Test roundtrip with empty spec."""
        spec: Spec = {}
        formatted = to_format(spec)
        result = from_format(formatted)
        assert result == spec

    def test_produces_valid_wiring_spec(
        self,
        to_format: "Callable[[Spec], str]",
        from_format: "Callable[[str], Spec]",
    ) -> None:
        """Test that formatted spec produces a valid Wiring spec."""
        spec: Spec = {"collections.OrderedDict mydict": {}}
        formatted = to_format(spec)
        parsed = from_format(formatted)
        wiring = Wiring(parsed)
        obj = wiring.mydict()
        assert obj is not None


class TestJsonFormat:
    """Tests specific to JSON format."""

    def test_roundtrip_with_none(self) -> None:
        """Test JSON roundtrip with None specifically."""
        spec: Spec = {"none_const": None}
        assert json_to_spec(spec_to_json(spec)) == spec


class TestTomlFormat:
    """Tests specific to TOML format."""

    def test_toplevel_constants(self) -> None:
        """Test that top-level keys become constants."""
        toml_str = """
my_value = 123

["datetime.datetime now"]
year = "{my_value}"
"""
        spec = toml_to_spec(toml_str)
        assert "my_value" in spec
        assert spec["my_value"] == 123


class TestIniFormat:
    """Tests specific to INI format."""

    def test_constants_section_extraction(self) -> None:
        """Test that constants are extracted from [constants] section."""
        ini_str = """
[constants]
my_value = 123

[datetime.datetime now]
year = {my_value}
"""
        spec = ini_to_spec(ini_str)
        assert "my_value" in spec
        assert spec["my_value"] == 123
        assert "constants" not in spec

    @pytest.mark.parametrize(
        "val, expected",
        [
            ("true", True),
            ("True", True),
            ("TRUE", True),
            ("false", False),
            ("False", False),
            ("FALSE", False),
        ],
    )
    def test_parse_boolean_case_insensitive(
        self, val: str, expected: bool
    ) -> None:
        """Test that boolean values parse case-insensitively."""
        ini_str = f"[constants]\nflag = {val}\n"
        spec = ini_to_spec(ini_str)
        assert spec["flag"] is expected


class TestCrossFormatCompatibility:
    """Tests for cross-format compatibility."""

    def test_json_to_toml_to_json(self) -> None:
        """Test converting JSON -> TOML -> JSON preserves data."""
        spec: Spec = {
            "datetime.datetime now": {"year": "{year}"},
            "year": 2025,
        }
        json_str = spec_to_json(spec)
        spec_from_json = json_to_spec(json_str)
        toml_str = spec_to_toml(spec_from_json)
        spec_from_toml = toml_to_spec(toml_str)
        json_str_2 = spec_to_json(spec_from_toml)
        final_spec = json_to_spec(json_str_2)
        assert final_spec == spec


class TestFormatErrorHandling:
    """Tests for FormatError handling in parsing functions."""

    @pytest.mark.parametrize(
        "parser, content, fmt, msg",
        [
            (
                json_to_spec,
                '{"invalid": json content}',
                "json",
                "Failed to parse JSON content",
            ),
            (
                toml_to_spec,
                '["invalid toml content',
                "toml",
                "Failed to parse TOML content",
            ),
            (
                ini_to_spec,
                "[invalid section\nkey = value",
                "ini",
                "Failed to parse INI content",
            ),
        ],
    )
    def test_parsing_errors(
        self,
        parser: "Callable[[str], Spec]",
        content: str,
        fmt: str,
        msg: str,
    ) -> None:
        """Test parsing error handling for various formats."""
        from apywire.exceptions import FormatError

        with pytest.raises(FormatError) as exc_info:
            parser(content)

        assert exc_info.value.format == fmt
        assert msg in str(exc_info.value)

    def test_toml_write_error(self) -> None:
        """Test TOML write error when tomli_w is not available."""
        # Temporarily disable tomli_w
        import apywire.formats
        from apywire.exceptions import FormatError

        original_tomli_w = apywire.formats._tomli_w
        apywire.formats._tomli_w = None

        try:
            spec: Spec = {"collections.OrderedDict mydict": {}}
            with pytest.raises(FormatError) as exc_info:
                spec_to_toml(spec)

            assert exc_info.value.format == "toml"
            assert "TOML output requires tomli_w" in str(exc_info.value)

        finally:
            # Restore tomli_w
            apywire.formats._tomli_w = original_tomli_w


class TestNumericKeyConversion:
    """Tests for numeric key conversion across formats."""

    @pytest.mark.parametrize(
        "from_format, content",
        [
            (
                toml_to_spec,
                '["datetime.datetime dt"]\n0 = 2025\n1 = 6\n2 = 15\n',
            ),
            (
                json_to_spec,
                '{"datetime.datetime dt": {"0": 2025, "1": 6, "2": 15}}',
            ),
            (
                ini_to_spec,
                "[datetime.datetime dt]\n0 = 2025\n1 = 6\n2 = 15\n",
            ),
        ],
        ids=["toml", "json", "ini"],
    )
    def test_top_level_numeric_keys_become_ints(
        self, from_format: Callable[[str], Spec], content: str
    ) -> None:
        """Top-level numeric keys become int for positional args."""
        spec = from_format(content)
        entry = spec["datetime.datetime dt"]
        assert isinstance(entry, dict)
        assert 0 in entry
        assert 1 in entry
        assert 2 in entry
        assert entry[0] == 2025

    @pytest.mark.parametrize(
        "from_format, content",
        [
            (
                toml_to_spec,
                '["myapp.Config cfg"]\n'
                'codes = {"404" = "not found", "500" = "server error"}\n',
            ),
            (
                json_to_spec,
                '{"myapp.Config cfg": {"codes":'
                ' {"404": "not found",'
                ' "500": "server error"}}}',
            ),
        ],
        ids=["toml", "json"],
    )
    def test_nested_numeric_keys_stay_strings(
        self, from_format: Callable[[str], Spec], content: str
    ) -> None:
        """Nested numeric keys stay as strings."""
        spec = from_format(content)
        entry = spec["myapp.Config cfg"]
        assert isinstance(entry, dict)
        codes = entry["codes"]
        assert isinstance(codes, dict)
        # Nested keys should remain strings
        assert "404" in codes
        assert "500" in codes
        assert 404 not in codes

    def test_leading_zero_keys_stay_strings(self) -> None:
        """Keys with leading zeros must not be converted."""
        spec = toml_to_spec(
            '["myapp.Config cfg"]\n'
            '00 = "a"\n'
            '01 = "b"\n'
            '0 = "c"\n'
        )
        entry = spec["myapp.Config cfg"]
        assert isinstance(entry, dict)
        # "0" is canonical → converted to int
        assert 0 in entry
        # "00" and "01" have leading zeros → stay strings
        assert "00" in entry
        assert "01" in entry

    def test_json_root_must_be_object(self) -> None:
        """json_to_spec raises FormatError for non-object roots."""
        from apywire.exceptions import FormatError

        with pytest.raises(FormatError, match="root must be an object"):
            json_to_spec("[1, 2, 3]")

        with pytest.raises(FormatError, match="root must be an object"):
            json_to_spec('"just a string"')
