# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

import subprocess
import sys
from io import StringIO
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest

from apywire.__main__ import main


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
    # aio=True generates sync methods + .aio property
    assert "def d(self):" in output
    assert "cached_property" in output
    assert "CompiledAio" in output


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


def test_cli_compile_emit_spec_includes_spec_literal() -> None:
    """--emit-spec adds the source spec to the generated module."""
    spec_json = '{"y": 2025, "datetime.date d": {"year": "{y}"}}'
    with patch("sys.stdin", StringIO(spec_json)):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            result = main(["compile", "--format", "json", "--emit-spec", "-"])

    assert result == 0
    output = mock_stdout.getvalue()
    assert "spec = {" in output
    assert "'{y}'" in output


def test_cli_compile_without_emit_spec_omits_spec_literal() -> None:
    """Without --emit-spec the generated module is unchanged."""
    spec_json = '{"y": 2025, "datetime.date d": {"year": "{y}"}}'
    with patch("sys.stdin", StringIO(spec_json)):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            result = main(["compile", "--format", "json", "-"])

    assert result == 0
    assert "spec = {" not in mock_stdout.getvalue()


def test_cli_compile_emit_spec_unemittable_spec_errors() -> None:
    """A spec that cannot be emitted fails with a message, not a trace."""
    spec_json = '{"spec.Thing x": {}}'
    with patch("sys.stdin", StringIO(spec_json)):
        with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            result = main(["compile", "--format", "json", "--emit-spec", "-"])

    assert result == 1
    assert "Error compiling spec" in mock_stderr.getvalue()


def test_cli_merge_overlays_specs_and_prints_result() -> None:
    """merge prints the effective spec, so a config can be inspected."""
    base = '{"y": 1, "datetime.date d": {"year": "{y}"}}'
    with patch("sys.stdin", StringIO(base)):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            result = main(["merge", "--format", "json", "-"])

    assert result == 0
    assert '"y": 1' in mock_stdout.getvalue()


def test_cli_merge_converts_between_formats() -> None:
    """The output format defaults to the input's, and can be chosen."""
    base = '{"y": 1}'
    with patch("sys.stdin", StringIO(base)):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            result = main(
                ["merge", "--format", "json", "--output-format", "ini", "-"]
            )

    assert result == 0
    assert "y = 1" in mock_stdout.getvalue()


class SpecModule(ModuleType):
    """A module exposing an emitted spec, as --emit-spec produces."""

    def __init__(self, name: str, spec: object) -> None:
        super().__init__(name)
        self.spec = spec


def test_cli_merge_overlays_files(tmp_path: Path) -> None:
    """Specs are read from files, in overlay order."""
    base = tmp_path / "base.json"
    base.write_text('{"y": 1, "z": 1}')
    user = tmp_path / "user.json"
    user.write_text('{"y": 9}')

    with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
        result = main(["merge", "--format", "json", str(base), str(user)])

    assert result == 0
    output = mock_stdout.getvalue()
    assert '"y": 9' in output
    assert '"z": 1' in output


def test_cli_merge_reads_a_spec_from_an_importable_name() -> None:
    """A compiled container's emitted spec is a valid merge source."""
    sys.modules["cli_spec_module"] = SpecModule("cli_spec_module", {"y": 1})
    try:
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            result = main(
                ["merge", "--format", "json", "cli_spec_module:spec"]
            )
    finally:
        del sys.modules["cli_spec_module"]

    assert result == 0
    assert '"y": 1' in mock_stdout.getvalue()


def test_cli_merge_importable_name_that_is_not_a_spec_errors() -> None:
    """Pointing at a non-dict attribute fails with a message."""
    sys.modules["cli_bad_module"] = SpecModule("cli_bad_module", "not a spec")
    try:
        with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            result = main(["merge", "--format", "json", "cli_bad_module:spec"])
    finally:
        del sys.modules["cli_bad_module"]

    assert result == 1
    assert "not a spec dict" in mock_stderr.getvalue()


def test_cli_merge_missing_file_errors() -> None:
    """An unreadable source is reported, not traced."""
    with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
        result = main(["merge", "--format", "json", "/nonexistent/spec.json"])

    assert result == 1
    assert "Error reading" in mock_stderr.getvalue()


def test_cli_merge_unmergeable_specs_error() -> None:
    """A merge failure is a message and exit 1, not a traceback."""
    bad = '{"pkg.C c": {"-x": [1]}}'
    with patch("sys.stdin", StringIO(bad)):
        with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            result = main(["merge", "--format", "json", "-"])

    assert result == 1
    assert "Error merging specs" in mock_stderr.getvalue()
    assert "unknown merge marker" in mock_stderr.getvalue()


def test_cli_merge_unwritable_output_format_errors() -> None:
    """A serializer that cannot run is reported, not traced."""
    with patch("sys.stdin", StringIO('{"y": 1}')):
        with patch("apywire.__main__.spec_to_toml") as to_toml:
            to_toml.side_effect = ValueError("TOML output requires tomli_w.")
            with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
                result = main(
                    [
                        "merge",
                        "--format",
                        "json",
                        "--output-format",
                        "toml",
                        "-",
                    ]
                )

    assert result == 1
    assert "Error writing TOML" in mock_stderr.getvalue()
