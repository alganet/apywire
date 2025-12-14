# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

"""Spec format adapters for INI, TOML, and JSON serialization."""

from __future__ import annotations

import configparser
import json
from types import ModuleType
from typing import cast

from apywire.exceptions import FormatError
from apywire.wiring import Spec, _ConstantValue, _SpecMapping

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[import-not-found,no-redef]

_tomli_w: ModuleType | None = None
try:
    import importlib

    _tomli_w = importlib.import_module("tomli_w")
except ImportError:
    # tomli_w is optional; if not available, TOML output will be disabled and
    # handled at runtime.
    pass


def _serialize_ini_value(value: object) -> str:
    """Serialize a value for INI format."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value
    return json.dumps(value)


def _parse_ini_value(value: str) -> _ConstantValue | _SpecMapping:
    """Parse an INI value to Python type."""
    if value == "":
        return None
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    if value.startswith(("[", "{")):
        try:
            result: _ConstantValue | _SpecMapping = json.loads(value)
            return result
        except json.JSONDecodeError:
            pass
    return value


def spec_to_ini(spec: Spec) -> str:
    """Convert a spec dict to INI format string.

    Args:
        spec: The spec dictionary to serialize.

    Returns:
        INI-formatted string representation of the spec.

    Example:
        >>> spec = {"datetime.datetime now": {"year": "{y}"}, "y": 2025}
        >>> print(spec_to_ini(spec))
        [datetime.datetime now]
        year = {y}

        [constants]
        y = 2025
    """
    config = configparser.ConfigParser()
    for key, value in spec.items():
        if isinstance(value, dict):
            config[key] = {}
            for k, v in value.items():
                config[key][str(k)] = _serialize_ini_value(v)
        else:
            if "constants" not in config:
                config["constants"] = {}
            config["constants"][key] = _serialize_ini_value(value)
    output_lines: list[str] = []
    for section in config.sections():
        output_lines.append(f"[{section}]")
        for k, v in config[section].items():
            output_lines.append(f"{k} = {v}")
        output_lines.append("")
    return "\n".join(output_lines)


def ini_to_spec(content: str) -> Spec:
    """Parse INI content to a spec dict.

    Args:
        content: INI-formatted string to parse.

    Returns:
        Parsed spec dictionary.

    Raises:
        FormatError: If the content cannot be parsed as valid INI.

    Example:
        >>> ini = '''
        ... [datetime.datetime now]
        ... year = {now_year}
        ...
        ... [constants]
        ... now_year = 2025
        ... '''
        >>> spec = ini_to_spec(ini)
        >>> spec["now_year"]
        2025
    """
    try:
        config = configparser.ConfigParser()
        config.read_string(content)
    except Exception as e:
        raise FormatError("ini", f"Failed to parse INI content: {e}") from e

    spec: Spec = {}
    section_list: list[str] = config.sections()
    for section in section_list:
        if section == "constants":
            key_list: list[str] = list(config[section].keys())
            for key in key_list:
                value: str = config[section][key]
                parsed = _parse_ini_value(value)
                spec[key] = cast(_ConstantValue, parsed)
        else:
            section_dict: dict[str | int, _ConstantValue] = {}
            key_list = list(config[section].keys())
            for key in key_list:
                value = config[section][key]
                parsed = _parse_ini_value(value)
                section_dict[key] = cast(_ConstantValue, parsed)
            spec[section] = cast(_SpecMapping, section_dict)
    return spec


def spec_to_toml(spec: Spec) -> str:
    """Convert a spec dict to TOML format string.

    Constants are placed as top-level keys, wiring entries as tables.

    Args:
        spec: The spec dictionary to serialize.

    Returns:
        TOML-formatted string representation of the spec.

    Raises:
        FormatError: If tomli_w is not installed.

    Example:
        >>> spec = {"datetime.datetime now": {"year": "{y}"}, "y": 2025}
        >>> print(spec_to_toml(spec))
        y = 2025

        ["datetime.datetime now"]
        year = "{y}"
    """
    if _tomli_w is None:
        raise FormatError("toml", "TOML output requires tomli_w.")
    toml_dict: dict[str, object] = {}
    for key, value in spec.items():
        toml_dict[key] = value
    result: str = _tomli_w.dumps(toml_dict)
    return result


def toml_to_spec(content: str) -> Spec:
    """Parse TOML content to a spec dict.

    Top-level keys become constants, tables become wiring entries.

    Args:
        content: TOML-formatted string to parse.

    Returns:
        Parsed spec dictionary.

    Raises:
        FormatError: If the content cannot be parsed as valid TOML.

    Example:
        >>> toml = '''
        ... now_year = 2025
        ...
        ... ["datetime.datetime now"]
        ... year = "{now_year}"
        ... '''
        >>> spec = toml_to_spec(toml)
        >>> spec["now_year"]
        2025
    """
    try:
        data: dict[str, object] = tomllib.loads(content)
    except Exception as e:
        raise FormatError("toml", f"Failed to parse TOML content: {e}") from e

    spec: Spec = {}
    for key, value in data.items():
        if isinstance(value, dict):
            spec[key] = cast(_SpecMapping, value)
        else:
            spec[key] = cast(_ConstantValue, value)
    return spec


def spec_to_json(spec: Spec) -> str:
    """Convert a spec dict to JSON format string.

    Args:
        spec: The spec dictionary to serialize.

    Returns:
        JSON-formatted string representation of the spec.

    Example:
        >>> spec = {"datetime.datetime now": {}, "now_year": 2025}
        >>> print(spec_to_json(spec))
        {
          "datetime.datetime now": {},
          "now_year": 2025
        }
    """
    return json.dumps(spec, indent=2)


def json_to_spec(content: str) -> Spec:
    """Parse JSON content to a spec dict.

    Args:
        content: JSON-formatted string to parse.

    Returns:
        Parsed spec dictionary.

    Raises:
        FormatError: If the content cannot be parsed as valid JSON.

    Example:
        >>> json_str = '{"datetime.datetime now": {}, "now_year": 2025}'
        >>> spec = json_to_spec(json_str)
        >>> spec["now_year"]
        2025
    """
    try:
        result: Spec = json.loads(content)
    except Exception as e:
        raise FormatError("json", f"Failed to parse JSON content: {e}") from e

    return result
