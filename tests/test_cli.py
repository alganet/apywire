# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

import subprocess
import sys
from io import StringIO
from unittest.mock import patch

import pytest

from apywire.__main__ import main


def test_cli_version_short_flag() -> None:
    """Test CLI version display with -v flag."""
    with pytest.raises(SystemExit) as exc_info:
        main(["-v"])

    # argparse with action="version" exits with code 0
    assert exc_info.value.code == 0


def test_cli_version_long_flag() -> None:
    """Test CLI version display with --version flag."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])

    # argparse with action="version" exits with code 0
    assert exc_info.value.code == 0


def test_cli_help_flag() -> None:
    """Test CLI help display with -h flag."""
    with pytest.raises(SystemExit) as exc_info:
        main(["-h"])

    # argparse with action="help" exits with code 0
    assert exc_info.value.code == 0


def test_cli_help_long_flag() -> None:
    """Test CLI help display with --help flag."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])

    # argparse with action="help" exits with code 0
    assert exc_info.value.code == 0


def test_cli_no_arguments() -> None:
    """Test CLI with no arguments returns 0."""
    result = main([])
    assert result == 0


def test_cli_version_output_contains_package_name() -> None:
    """Test that version output contains 'apywire'."""
    from importlib.metadata import version

    expected_version = version("apywire")

    # Capture stdout since argparse writes version to stdout
    with pytest.raises(SystemExit) as exc_info:
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            main(["--version"])

    assert exc_info.value.code == 0
    stdout_output = mock_stdout.getvalue()
    assert "apywire" in stdout_output
    assert expected_version in stdout_output


def test_cli_version_short_output_contains_package_name() -> None:
    """Test that -v output contains 'apywire'."""
    from importlib.metadata import version

    expected_version = version("apywire")

    # Capture stdout since argparse writes version to stdout
    with pytest.raises(SystemExit) as exc_info:
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            main(["-v"])

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


def test_cli_generate_json() -> None:
    """Test generate command with JSON format."""
    with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
        result = main(
            ["generate", "--format", "json", "collections.OrderedDict d"]
        )

    assert result == 0
    output = mock_stdout.getvalue()
    assert "collections.OrderedDict d" in output


def test_cli_generate_ini() -> None:
    """Test generate command with INI format."""
    with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
        result = main(
            ["generate", "--format", "ini", "collections.OrderedDict d"]
        )

    assert result == 0
    output = mock_stdout.getvalue()
    assert "[collections.OrderedDict d]" in output


def test_cli_generate_toml() -> None:
    """Test generate command with TOML format."""
    with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
        result = main(
            ["generate", "--format", "toml", "collections.OrderedDict d"]
        )

    assert result == 0
    output = mock_stdout.getvalue()
    assert '["collections.OrderedDict d"]' in output


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


def test_cli_compile_json_stdin() -> None:
    """Test compile command with JSON from stdin."""
    json_input = '{"collections.OrderedDict d": {}}'
    with patch("sys.stdin", StringIO(json_input)):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            result = main(["compile", "--format", "json", "-"])

    assert result == 0
    output = mock_stdout.getvalue()
    assert "class Compiled:" in output
    assert "def d(self):" in output


def test_cli_compile_ini_stdin() -> None:
    """Test compile command with INI from stdin."""
    ini_input = "[collections.OrderedDict d]\n"
    with patch("sys.stdin", StringIO(ini_input)):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            result = main(["compile", "--format", "ini", "-"])

    assert result == 0
    output = mock_stdout.getvalue()
    assert "class Compiled:" in output


def test_cli_compile_toml_stdin() -> None:
    """Test compile command with TOML from stdin."""
    toml_input = '["collections.OrderedDict d"]\n'
    with patch("sys.stdin", StringIO(toml_input)):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            result = main(["compile", "--format", "toml", "-"])

    assert result == 0
    output = mock_stdout.getvalue()
    assert "class Compiled:" in output


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


def test_cli_compile_json_parsing_error() -> None:
    """Test CLI error handling for invalid JSON input."""
    json_input = '{"invalid": json content}'

    with patch("sys.stdin", StringIO(json_input)):
        with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            result = main(["compile", "--format", "json", "-"])

    assert result == 1  # Should return error code
    stderr_output = mock_stderr.getvalue()
    assert "Error parsing JSON content:" in stderr_output


def test_cli_compile_toml_parsing_error() -> None:
    """Test CLI error handling for invalid TOML input."""
    toml_input = '["invalid toml content'

    with patch("sys.stdin", StringIO(toml_input)):
        with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            result = main(["compile", "--format", "toml", "-"])

    assert result == 1  # Should return error code
    stderr_output = mock_stderr.getvalue()
    assert "Error parsing TOML content:" in stderr_output


def test_cli_compile_ini_parsing_error() -> None:
    """Test CLI error handling for invalid INI input."""
    ini_input = "[invalid section\nkey = value"

    with patch("sys.stdin", StringIO(ini_input)):
        with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            result = main(["compile", "--format", "ini", "-"])

    assert result == 1  # Should return error code
    stderr_output = mock_stderr.getvalue()
    assert "Error parsing INI content:" in stderr_output


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
