# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

import argparse
import subprocess
import sys
from io import StringIO
from typing import cast
from unittest.mock import patch

import pytest

from apywire.__main__ import cmd_compile, cmd_generate, main


@pytest.mark.parametrize(
    "flag",
    ["-v", "--version", "-h", "--help"],
    ids=["v", "version", "h", "help"],
)
def test_cli_basic_flags_exit_zero(flag: str) -> None:
    """Test that basic CLI flags exit with code 0."""
    with pytest.raises(SystemExit) as exc_info:
        main([flag])
    assert exc_info.value.code == 0


def test_cli_no_arguments() -> None:
    """Test CLI with no arguments returns 0."""
    result = main([])
    assert result == 0


@pytest.mark.parametrize("flag", ["-v", "--version"], ids=["v", "version"])
def test_cli_version_output_format(flag: str) -> None:
    """Test that version output contains package name and version."""
    from importlib.metadata import version

    expected_version = version("apywire")
    with pytest.raises(SystemExit) as exc_info:
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            main([flag])

    assert exc_info.value.code == 0
    stdout_output = mock_stdout.getvalue()
    assert "apywire" in stdout_output
    assert expected_version in stdout_output


def test_cli_help_output_format() -> None:
    """Test that help output has expected format."""
    # Capture stdout since argparse writes help to stdout
    with pytest.raises(SystemExit) as exc_info:
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            main(["--help"])

    assert exc_info.value.code == 0
    stdout_output = mock_stdout.getvalue()
    assert "usage: apywire" in stdout_output
    assert "dependency injection" in stdout_output
    assert "-h, --help" in stdout_output
    assert "-v, --version" in stdout_output


def test_cli_invalid_argument_handling() -> None:
    """Test CLI handling of invalid arguments."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--invalid-flag"])

    # argparse exits with code 2 for invalid arguments
    assert exc_info.value.code == 2


def test_cli_version_dynamic_from_metadata() -> None:
    """Test that version is fetched dynamically from package metadata."""
    from importlib.metadata import version

    # Verify we can get the version dynamically
    pkg_version = version("apywire")
    assert isinstance(pkg_version, str)
    assert len(pkg_version) > 0

    # Test that the CLI uses the same dynamic version
    with pytest.raises(SystemExit) as exc_info:
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            main(["--version"])

    assert exc_info.value.code == 0
    stdout_output = mock_stdout.getvalue()
    assert f"apywire {pkg_version}" in stdout_output


def test_cli_both_version_flags_behave_identically() -> None:
    """Test that -v and --version produce identical behavior."""
    from importlib.metadata import version

    expected_output = f"apywire {version('apywire')}"

    # Test -v flag
    with pytest.raises(SystemExit) as exc_info_v:
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout_v:
            main(["-v"])

    output_v = mock_stdout_v.getvalue()

    # Test --version flag
    with pytest.raises(SystemExit) as exc_info_version:
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout_version:
            main(["--version"])

    output_version = mock_stdout_version.getvalue()

    # Both should exit successfully and produce same output
    assert expected_output == output_v.strip() == output_version.strip()
    assert exc_info_v.value.code == exc_info_version.value.code == 0


def test_cli_module_execution() -> None:
    """Test that the module can be executed as __main__."""
    # This tests that the module structure works correctly
    result = subprocess.run(
        [sys.executable, "-m", "apywire", "--version"],
        capture_output=True,
        text=True,
    )

    # Should exit successfully and output version
    assert result.returncode == 0
    assert "apywire" in result.stdout  # argparse outputs to stdout


@pytest.mark.parametrize(
    "fmt, expected_marker",
    [
        ("json", "collections.OrderedDict d"),
        ("ini", "[collections.OrderedDict d]"),
        ("toml", '["collections.OrderedDict d"]'),
    ],
    ids=["json", "ini", "toml"],
)
def test_cli_generate_formats(fmt: str, expected_marker: str) -> None:
    """Test generate command with different output formats."""
    with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
        result = main(
            ["generate", "--format", fmt, "collections.OrderedDict d"]
        )

    assert result == 0
    output = mock_stdout.getvalue()
    assert expected_marker in output


def test_cli_generate_multiple_entries() -> None:
    """Test generate command with multiple entries."""
    with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
        result = main(
            [
                "generate",
                "--format",
                "json",
                "collections.OrderedDict a",
                "collections.OrderedDict b",
            ]
        )

    assert result == 0
    output = mock_stdout.getvalue()
    assert "collections.OrderedDict a" in output
    assert "collections.OrderedDict b" in output


@pytest.mark.parametrize(
    "fmt, input_data",
    [
        ("json", '{"collections.OrderedDict d": {}}'),
        ("ini", "[collections.OrderedDict d]\n"),
        ("toml", '["collections.OrderedDict d"]\n'),
    ],
    ids=["json", "ini", "toml"],
)
def test_cli_compile_stdin_formats(fmt: str, input_data: str) -> None:
    """Test compile command with different input formats from stdin."""
    with patch("sys.stdin", StringIO(input_data)):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            result = main(["compile", "--format", fmt, "-"])

    assert result == 0
    output = mock_stdout.getvalue()
    assert "class Compiled:" in output
    assert "def d(self):" in output


def test_cli_compile_with_aio_flag() -> None:
    """Test compile command with --aio flag."""
    json_input = '{"collections.OrderedDict d": {}}'
    with patch("sys.stdin", StringIO(json_input)):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            result = main(["compile", "--format", "json", "--aio", "-"])

    assert result == 0
    output = mock_stdout.getvalue()
    assert "async def d(self):" in output


def test_cli_compile_with_thread_safe_flag() -> None:
    """Test compile command with --thread-safe flag."""
    json_input = '{"collections.OrderedDict d": {}}'
    with patch("sys.stdin", StringIO(json_input)):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            result = main(
                ["compile", "--format", "json", "--thread-safe", "-"]
            )

    assert result == 0
    output = mock_stdout.getvalue()
    assert "class Compiled(ThreadSafeMixin):" in output


def test_cli_compile_from_file() -> None:
    """Test compile command reading from a file."""
    import os
    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as f:
        f.write('{"collections.OrderedDict d": {}}')
        temp_file = f.name

    try:
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            result = main(["compile", "--format", "json", temp_file])

        assert result == 0
        output = mock_stdout.getvalue()
        assert "class Compiled:" in output
    finally:
        os.unlink(temp_file)


@pytest.mark.parametrize(
    "fmt, input_data, expected_err",
    [
        ("json", '{"invalid": json content}', "Error parsing JSON content:"),
        ("toml", '["invalid toml content', "Error parsing TOML content:"),
        ("ini", "[invalid section\nkey = value", "Error parsing INI content:"),
    ],
    ids=["json", "toml", "ini"],
)
def test_cli_compile_parsing_errors(
    fmt: str, input_data: str, expected_err: str
) -> None:
    """Test CLI error handling for invalid input formats."""
    with patch("sys.stdin", StringIO(input_data)):
        with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            result = main(["compile", "--format", fmt, "-"])

    assert result == 1
    stderr_output = mock_stderr.getvalue()
    assert expected_err in stderr_output


def test_cli_generate_reports_generation_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fail(*args: object, **kwargs: object) -> list[str]:
        raise RuntimeError("explode")

    monkeypatch.setattr("apywire.__main__.Generator.generate", _fail)

    with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
        result = main(
            ["generate", "--format", "json", "collections.OrderedDict d"]
        )

    assert result == 1
    assert "Error generating specification" in mock_stderr.getvalue()


def test_cli_generate_unknown_format_returns_error() -> None:
    args = argparse.Namespace(
        format="yaml", entries=cast(list[str], ["collections.OrderedDict d"])
    )

    with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
        result = cmd_generate(args)

    assert result == 1
    assert "Unknown format: yaml" in mock_stderr.getvalue()


def test_cli_compile_unknown_format_returns_error() -> None:
    args = argparse.Namespace(
        format="yaml",
        aio=False,
        thread_safe=False,
        input_file="-",
    )

    with patch("sys.stdin", StringIO("{}")):
        with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            result = cmd_compile(args)

    assert result == 1
    assert "Unknown format: yaml" in mock_stderr.getvalue()


def test_cli_compile_missing_file_returns_error() -> None:
    with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
        result = main(["compile", "--format", "json", "missing-file.json"])

    assert result == 1
    assert "Error reading file" in mock_stderr.getvalue()


def test_cli_generate_toml_write_error() -> None:
    """Test CLI error handling for TOML write when tomli_w is not available."""
    # Temporarily disable tomli_w
    import apywire.formats

    original_tomli_w = apywire.formats._tomli_w
    apywire.formats._tomli_w = None

    try:
        with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            result = main(
                ["generate", "--format", "toml", "collections.OrderedDict d"]
            )

        assert result == 1  # Should return error code
        stderr_output = mock_stderr.getvalue()
        assert "Error generating TOML output:" in stderr_output
        assert "TOML output requires tomli_w" in stderr_output

    finally:
        # Restore tomli_w
        apywire.formats._tomli_w = original_tomli_w
