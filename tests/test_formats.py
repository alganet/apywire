# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

"""Tests for spec format adapters."""

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


class TestJsonFormat:
    """Tests for JSON format adapter."""

    def test_roundtrip_simple_spec(self) -> None:
        """Test JSON roundtrip with simple spec."""
        spec: Spec = {
            "datetime.datetime now": {"year": "{now_year}"},
            "now_year": 2025,
        }
        json_str = spec_to_json(spec)
        result = json_to_spec(json_str)
        assert result == spec

    def test_roundtrip_with_constants(self) -> None:
        """Test JSON roundtrip with various constant types."""
        spec: Spec = {
            "datetime.datetime now": {},
            "str_const": "hello",
            "int_const": 42,
            "float_const": 3.14,
            "bool_const": True,
            "none_const": None,
        }
        json_str = spec_to_json(spec)
        result = json_to_spec(json_str)
        assert result == spec

    def test_roundtrip_with_nested_data(self) -> None:
        """Test JSON roundtrip with nested lists and dicts."""
        spec: Spec = {
            "mymod.MyClass obj": {
                "items": [1, 2, 3],
                "config": {"key": "value"},
            },
        }
        json_str = spec_to_json(spec)
        result = json_to_spec(json_str)
        assert result == spec

    def test_roundtrip_empty_spec(self) -> None:
        """Test JSON roundtrip with empty spec."""
        spec: Spec = {}
        json_str = spec_to_json(spec)
        result = json_to_spec(json_str)
        assert result == spec

    def test_produces_valid_wiring_spec(self) -> None:
        """Test that parsed JSON produces a valid Wiring spec."""
        json_str = '{"collections.OrderedDict mydict": {}}'
        spec = json_to_spec(json_str)
        wiring = Wiring(spec)
        obj = wiring.mydict()
        assert obj is not None


class TestTomlFormat:
    """Tests for TOML format adapter."""

    def test_roundtrip_simple_spec(self) -> None:
        """Test TOML roundtrip with simple spec."""
        spec: Spec = {
            "datetime.datetime now": {"year": "{now_year}"},
            "now_year": 2025,
        }
        toml_str = spec_to_toml(spec)
        result = toml_to_spec(toml_str)
        assert result == spec

    def test_roundtrip_with_constants(self) -> None:
        """Test TOML roundtrip with various constant types."""
        spec: Spec = {
            "datetime.datetime now": {},
            "str_const": "hello",
            "int_const": 42,
            "float_const": 3.14,
            "bool_const": True,
        }
        toml_str = spec_to_toml(spec)
        result = toml_to_spec(toml_str)
        assert result == spec

    def test_roundtrip_with_nested_data(self) -> None:
        """Test TOML roundtrip with nested lists and dicts."""
        spec: Spec = {
            "mymod.MyClass obj": {
                "items": [1, 2, 3],
            },
        }
        toml_str = spec_to_toml(spec)
        result = toml_to_spec(toml_str)
        assert result == spec

    def test_roundtrip_empty_spec(self) -> None:
        """Test TOML roundtrip with empty spec."""
        spec: Spec = {}
        toml_str = spec_to_toml(spec)
        result = toml_to_spec(toml_str)
        assert result == spec

    def test_produces_valid_wiring_spec(self) -> None:
        """Test that parsed TOML produces a valid Wiring spec."""
        toml_str = '["collections.OrderedDict mydict"]\n'
        spec = toml_to_spec(toml_str)
        wiring = Wiring(spec)
        obj = wiring.mydict()
        assert obj is not None

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
    """Tests for INI format adapter."""

    def test_roundtrip_simple_spec(self) -> None:
        """Test INI roundtrip with simple spec."""
        spec: Spec = {
            "datetime.datetime now": {"year": "{now_year}"},
            "now_year": 2025,
        }
        ini_str = spec_to_ini(spec)
        result = ini_to_spec(ini_str)
        assert result == spec

    def test_roundtrip_string_constant(self) -> None:
        """Test INI roundtrip with string constant."""
        spec: Spec = {
            "datetime.datetime now": {},
            "my_str": "hello world",
        }
        ini_str = spec_to_ini(spec)
        result = ini_to_spec(ini_str)
        assert result == spec

    def test_roundtrip_numeric_constants(self) -> None:
        """Test INI roundtrip with numeric constants."""
        spec: Spec = {
            "datetime.datetime now": {},
            "int_val": 42,
            "float_val": 3.14,
        }
        ini_str = spec_to_ini(spec)
        result = ini_to_spec(ini_str)
        assert result == spec

    def test_roundtrip_boolean_constants(self) -> None:
        """Test INI roundtrip with boolean constants."""
        spec: Spec = {
            "datetime.datetime now": {},
            "true_val": True,
            "false_val": False,
        }
        ini_str = spec_to_ini(spec)
        result = ini_to_spec(ini_str)
        assert result == spec

    def test_roundtrip_none_constant(self) -> None:
        """Test INI roundtrip with None constant."""
        spec: Spec = {
            "datetime.datetime now": {},
            "none_val": None,
        }
        ini_str = spec_to_ini(spec)
        result = ini_to_spec(ini_str)
        assert result == spec

    def test_roundtrip_list_as_json(self) -> None:
        """Test INI roundtrip with list serialized as JSON."""
        spec: Spec = {
            "mymod.MyClass obj": {
                "items": [1, 2, 3],
            },
        }
        ini_str = spec_to_ini(spec)
        result = ini_to_spec(ini_str)
        assert result == spec

    def test_roundtrip_dict_as_json(self) -> None:
        """Test INI roundtrip with dict serialized as JSON."""
        spec: Spec = {
            "mymod.MyClass obj": {
                "config": {"key": "value"},
            },
        }
        ini_str = spec_to_ini(spec)
        result = ini_to_spec(ini_str)
        assert result == spec

    def test_roundtrip_empty_spec(self) -> None:
        """Test INI roundtrip with empty spec."""
        spec: Spec = {}
        ini_str = spec_to_ini(spec)
        result = ini_to_spec(ini_str)
        assert result == spec

    def test_produces_valid_wiring_spec(self) -> None:
        """Test that parsed INI produces a valid Wiring spec."""
        ini_str = "[collections.OrderedDict mydict]\n"
        spec = ini_to_spec(ini_str)
        wiring = Wiring(spec)
        obj = wiring.mydict()
        assert obj is not None

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

    def test_parse_true_case_insensitive(self) -> None:
        """Test that 'TRUE', 'True', 'true' all parse to True."""
        for val in ["true", "True", "TRUE"]:
            ini_str = f"[constants]\nflag = {val}\n"
            spec = ini_to_spec(ini_str)
            assert spec["flag"] is True

    def test_parse_false_case_insensitive(self) -> None:
        """Test that 'FALSE', 'False', 'false' all parse to False."""
        for val in ["false", "False", "FALSE"]:
            ini_str = f"[constants]\nflag = {val}\n"
            spec = ini_to_spec(ini_str)
            assert spec["flag"] is False


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

    def test_all_formats_produce_working_wiring(self) -> None:
        """Test that all formats produce specs that work with Wiring."""
        spec: Spec = {
            "collections.OrderedDict mydict": {},
        }

        for to_format, from_format in [
            (spec_to_json, json_to_spec),
            (spec_to_toml, toml_to_spec),
            (spec_to_ini, ini_to_spec),
        ]:
            formatted = to_format(spec)
            parsed = from_format(formatted)
            wiring = Wiring(parsed)
            obj = wiring.mydict()
            assert obj is not None


class TestFormatErrorHandling:
    """Tests for FormatError handling in parsing functions."""

    def test_json_parsing_error(self) -> None:
        """Test JSON parsing error handling."""
        from apywire.exceptions import FormatError

        invalid_json = '{"invalid": json content}'
        with pytest.raises(FormatError) as exc_info:
            json_to_spec(invalid_json)

        assert exc_info.value.format == "json"
        assert "Failed to parse JSON content" in str(exc_info.value)

    def test_toml_parsing_error(self) -> None:
        """Test TOML parsing error handling."""
        from apywire.exceptions import FormatError

        invalid_toml = '["invalid toml content'
        with pytest.raises(FormatError) as exc_info:
            toml_to_spec(invalid_toml)

        assert exc_info.value.format == "toml"
        assert "Failed to parse TOML content" in str(exc_info.value)

    def test_ini_parsing_error(self) -> None:
        """Test INI parsing error handling."""
        from apywire.exceptions import FormatError

        invalid_ini = "[invalid section\nkey = value"
        with pytest.raises(FormatError) as exc_info:
            ini_to_spec(invalid_ini)

        assert exc_info.value.format == "ini"
        assert "Failed to parse INI content" in str(exc_info.value)

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
