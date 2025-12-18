# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

"""Command-line interface for apywire."""

from __future__ import annotations

import argparse
import sys
from importlib.metadata import version
from typing import Callable, cast

from apywire.compiler import WiringCompiler
from apywire.formats import (
    ini_to_spec,
    json_to_spec,
    spec_to_ini,
    spec_to_json,
    spec_to_toml,
    toml_to_spec,
)
from apywire.generator import Generator
from apywire.wiring import Spec


def cmd_generate(args: argparse.Namespace) -> int:
    """Handle the generate command."""
    entries: list[str] = cast(list[str], args.entries)
    fmt: str = cast(str, args.format)

    try:
        spec = Generator.generate(*entries)
    except Exception as e:
        print(f"Error generating specification: {e}", file=sys.stderr)
        return 1

    output: str
    try:
        if fmt == "ini":
            output = spec_to_ini(spec)
        elif fmt == "toml":
            output = spec_to_toml(spec)
        elif fmt == "json":
            output = spec_to_json(spec)
        else:
            print(f"Unknown format: {fmt}", file=sys.stderr)
            return 1
    except Exception as e:
        # Handle FormatError with user-friendly messages
        print(f"Error generating {fmt.upper()} output: {e}", file=sys.stderr)
        return 1

    print(output)
    return 0


def cmd_compile(args: argparse.Namespace) -> int:
    """Handle the compile command."""
    input_file: str = cast(str, args.input_file)
    fmt: str = cast(str, args.format)
    aio: bool = cast(bool, args.aio)
    thread_safe: bool = cast(bool, args.thread_safe)

    content: str
    if input_file == "-":
        content = sys.stdin.read()
    else:
        try:
            with open(input_file, encoding="utf-8") as f:
                content = f.read()
        except (FileNotFoundError, PermissionError, OSError) as e:
            print(f"Error reading file '{input_file}': {e}", file=sys.stderr)
            return 1

    spec: Spec
    try:
        if fmt == "ini":
            spec = ini_to_spec(content)
        elif fmt == "toml":
            spec = toml_to_spec(content)
        elif fmt == "json":
            spec = json_to_spec(content)
        else:
            print(f"Unknown format: {fmt}", file=sys.stderr)
            return 1
    except Exception as e:
        # Handle FormatError with user-friendly messages
        print(f"Error parsing {fmt.upper()} content: {e}", file=sys.stderr)
        return 1

    compiler = WiringCompiler(spec)
    code = compiler.compile(aio=aio, thread_safe=thread_safe)
    print(code)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="apywire",
        description="Generate and compile dependency injection specs.",
        epilog="Ex: apywire generate --format json 'datetime.datetime now'",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"apywire {version('apywire')}",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="command")

    generate_parser = subparsers.add_parser(
        "generate",
        help="Generate a spec from class entries",
        description=(
            "Introspect classes and generate a wiring spec with placeholders "
            "for constructor parameters. Output is written to stdout."
        ),
        epilog=(
            "Examples:\n"
            "  apywire generate --format json 'datetime.datetime now'\n"
            "  apywire generate --format toml 'myapp.Config cfg' > config.toml"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    generate_parser.add_argument(
        "--format",
        required=True,
        choices=["ini", "toml", "json"],
        metavar="FORMAT",
        help="Output format: ini, toml, or json (required)",
    )
    generate_parser.add_argument(
        "entries",
        nargs="+",
        metavar="ENTRY",
        help="Class entry as 'module.Class name'",
    )
    generate_parser.set_defaults(func=cmd_generate)

    compile_parser = subparsers.add_parser(
        "compile",
        help="Compile a spec file to Python code",
        description=(
            "Read a wiring spec file and compile it to Python code. "
            "The generated code contains a Compiled class with lazy accessors."
        ),
        epilog=(
            "Examples:\n"
            "  apywire compile --format json config.json\n"
            "  apywire compile --format toml --aio config.toml > wiring.py\n"
            "  cat spec.json | apywire compile --format json -"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    compile_parser.add_argument(
        "--format",
        required=True,
        choices=["ini", "toml", "json"],
        metavar="FORMAT",
        help="Input format: ini, toml, or json (required)",
    )
    compile_parser.add_argument(
        "--aio",
        action="store_true",
        help="Generate async def accessors using run_in_executor",
    )
    compile_parser.add_argument(
        "--thread-safe",
        action="store_true",
        help="Generate thread-safe accessors with locking",
    )
    compile_parser.add_argument(
        "input_file",
        metavar="FILE",
        help="Input spec file path, or '-' to read from stdin",
    )
    compile_parser.set_defaults(func=cmd_compile)

    args = parser.parse_args(argv)

    command: str | None = cast(str | None, args.command)
    if command is None:
        parser.print_help()
        return 0

    func: Callable[[argparse.Namespace], int] = cast(
        Callable[[argparse.Namespace], int], args.func
    )
    return func(args)


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    sys.exit(main())
