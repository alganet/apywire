# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

"""Command-line interface for apywire."""

from __future__ import annotations

import argparse
import importlib
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
from apywire.merge import merge_specs
from apywire.wiring import Spec

_FORMAT_CHOICES: tuple[str, ...] = ("ini", "toml", "json")


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


def _parse_spec(fmt: str, content: str) -> Spec:
    """Parse spec content in one of the supported formats."""
    if fmt == "ini":
        return ini_to_spec(content)
    if fmt == "toml":
        return toml_to_spec(content)
    return json_to_spec(content)


def _serialize_spec(fmt: str, spec: Spec) -> str:
    """Serialize a spec in one of the supported formats."""
    if fmt == "ini":
        return spec_to_ini(spec)
    if fmt == "toml":
        return spec_to_toml(spec)
    return spec_to_json(spec)


def _read_spec(source: str, fmt: str) -> Spec:
    """Read a spec from a file, from stdin, or from an importable name.

    The importable form (``pkg.module:name``) is what makes this useful
    against compiled defaults: a container emitted with ``--emit-spec``
    exposes its source spec as a module attribute, and that is exactly
    the base a user's config is overlaid onto.
    """
    if ":" in source:
        module_name, _, attr = source.partition(":")
        module = importlib.import_module(module_name)
        value = cast(object, getattr(module, attr))
        if not isinstance(value, dict):
            raise ValueError(
                f"'{source}' is a {type(value).__name__}, not a spec dict"
            )
        return cast(Spec, value)

    content: str
    if source == "-":
        content = sys.stdin.read()
    else:
        with open(source, encoding="utf-8") as f:
            content = f.read()
    return _parse_spec(fmt, content)


def cmd_merge(args: argparse.Namespace) -> int:
    """Handle the merge command."""
    fmt: str = cast(str, args.format)
    out_fmt: str = cast(str | None, args.output_format) or fmt
    sources: list[str] = cast("list[str]", args.sources)

    specs: list[Spec] = []
    for source in sources:
        try:
            specs.append(_read_spec(source, fmt))
        except Exception as e:
            print(f"Error reading '{source}': {e}", file=sys.stderr)
            return 1

    try:
        merged = merge_specs(specs[0], *specs[1:])
    except ValueError as e:
        print(f"Error merging specs: {e}", file=sys.stderr)
        return 1

    try:
        print(_serialize_spec(out_fmt, merged))
    except Exception as e:
        print(f"Error writing {out_fmt.upper()}: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_compile(args: argparse.Namespace) -> int:
    """Handle the compile command."""
    input_file: str = cast(str, args.input_file)
    fmt: str = cast(str, args.format)
    aio: bool = cast(bool, args.aio)
    thread_safe: bool = cast(bool, args.thread_safe)
    emit_spec: bool = cast(bool, args.emit_spec)

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
        spec = _parse_spec(fmt, content)
    except Exception as e:
        # Handle FormatError with user-friendly messages
        print(f"Error parsing {fmt.upper()} content: {e}", file=sys.stderr)
        return 1

    compiler = WiringCompiler(spec)
    try:
        code = compiler.compile(
            aio=aio, thread_safe=thread_safe, emit_spec=emit_spec
        )
    except ValueError as e:
        print(f"Error compiling spec: {e}", file=sys.stderr)
        return 1
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
        choices=_FORMAT_CHOICES,
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
            "  apywire compile --format toml --emit-spec defaults.toml\n"
            "  cat spec.json | apywire compile --format json -"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    compile_parser.add_argument(
        "--format",
        required=True,
        choices=_FORMAT_CHOICES,
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
        "--emit-spec",
        action="store_true",
        help="Also emit the source spec as a module-level dict",
    )
    compile_parser.add_argument(
        "input_file",
        metavar="FILE",
        help="Input spec file path, or '-' to read from stdin",
    )
    compile_parser.set_defaults(func=cmd_compile)

    merge_parser = subparsers.add_parser(
        "merge",
        help="Overlay spec files and print the effective spec",
        description=(
            "Overlay spec files left to right and print the result. Use it "
            "to see what a config actually merges to."
        ),
        epilog=(
            "Examples:\n"
            "  apywire merge --format toml defaults.toml user.toml\n"
            "  apywire merge --format toml --output-format json "
            "defaults.toml user.toml\n"
            "  apywire merge --format toml myapp._defaults:spec user.toml"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    merge_parser.add_argument(
        "--format",
        required=True,
        choices=_FORMAT_CHOICES,
        metavar="FORMAT",
        help="Input format: ini, toml, or json (required)",
    )
    merge_parser.add_argument(
        "--output-format",
        choices=_FORMAT_CHOICES,
        metavar="FORMAT",
        help="Output format (defaults to the input format)",
    )
    merge_parser.add_argument(
        "sources",
        metavar="SOURCE",
        nargs="+",
        help=(
            "Spec files, in overlay order: a path, '-' for stdin, or an "
            "importable 'pkg.module:name' (e.g. a compiled spec)"
        ),
    )
    merge_parser.set_defaults(func=cmd_merge)

    args = parser.parse_args(argv)

    command: str | None = cast(str | None, args.command)
    if command is None:
        parser.print_help()
        return 0

    func: Callable[[argparse.Namespace], int] = cast(
        Callable[[argparse.Namespace], int], args.func
    )
    return func(args)


if __name__ == "__main__":
    sys.exit(main())
