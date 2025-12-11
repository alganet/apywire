# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

"""Command-line interface for apywire."""

import argparse
import sys
from importlib.metadata import version


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="apywire",
        description="A package to wire up objects",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"apywire {version('apywire')}",
    )

    parser.parse_args(argv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
