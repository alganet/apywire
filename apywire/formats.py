# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

"""Spec format adapters for INI, TOML, and JSON serialization."""

from __future__ import annotations

import configparser
import json
from types import ModuleType
from collections.abc import Mapping
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
            spec[section] = cast(
                _SpecMapping,
                _convert_numeric_keys(section_dict),
            )
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
        if isinstance(value, dict):
            toml_dict[key] = _stringify_int_keys(value)
        else:
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
            spec[key] = cast(_SpecMapping, _convert_numeric_keys(value))
        else:
            spec[key] = cast(_ConstantValue, value)
    return spec


def _stringify_int_keys(
    d: Mapping[str | int, object],
) -> dict[str, object]:
    """Convert top-level integer keys back to strings for serialization.

    The inverse of ``_convert_numeric_keys``. Only converts the
    top level — nested dicts are left unchanged because only
    top-level int keys represent positional arguments.
    """
    return {str(k): v for k, v in d.items()}


def _convert_numeric_keys(
    d: Mapping[str | int, object],
) -> dict[str | int, object]:
    """Convert top-level numeric string keys to integers.

    File formats (TOML, JSON, INI) use string keys, but apywire
    uses integer keys for positional arguments. This converts
    keys like ``"0"``, ``"1"`` to ``0``, ``1``.

    Only converts the top level of the dict — nested dicts keep
    their string keys, since ``_separate_args_kwargs`` only checks
    the top level for positional vs keyword argument dispatch.
    """
    result: dict[str | int, object] = {}
    for k, v in d.items():
        # Only convert canonical decimal representations (no leading
        # zeros) to avoid "00"/"01" silently colliding with "0"/"1".
        new_key: str | int
        if isinstance(k, str) and k.isdigit() and str(int(k)) == k:
            new_key = int(k)
        else:
            new_key = k
        result[new_key] = v
    return result


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
        raw: object = json.loads(content)
    except Exception as e:
        raise FormatError(
            "json", f"Failed to parse JSON content: {e}"
        ) from e

    if not isinstance(raw, dict):
        raise FormatError(
            "json",
            "JSON root must be an object, "
            f"got {type(raw).__name__}",
        )

    data: dict[str, object] = raw
    spec: Spec = {}
    for key, value in data.items():
        if isinstance(value, dict):
            spec[key] = cast(_SpecMapping, _convert_numeric_keys(value))
        else:
            spec[key] = cast(_ConstantValue, value)
    return spec
