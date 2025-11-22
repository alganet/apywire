# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

# mypy: ignore-errors

import os

from Cython.Build import cythonize
from setuptools import setup


def extract_spdx_info(file_path):
    """Extract SPDX copyright and license from the file's header."""
    prefix = "# SPDX-"
    copyright_text = None
    license_id = None
    with open(file_path, "r") as f:
        for line in f:
            if line.startswith(f"{prefix}FileCopyrightText:"):
                copyright_text = line.split(":", 1)[1].strip()
            elif line.startswith(f"{prefix}License-Identifier:"):
                license_id = line.split(":", 1)[1].strip()
            if copyright_text and license_id:
                break
    if not copyright_text or not license_id:
        raise ValueError("SPDX information not found in the file header.")
    return copyright_text, license_id


COPYRIGHT, LICENSE = extract_spdx_info(__file__)


def add_spdx_header(c_file):
    prefix = "/* SPDX-"
    spdx_header = (
        f"{prefix}FileCopyrightText: {COPYRIGHT} */\n"
        f"{prefix}License-Identifier: {LICENSE} */\n"
    )
    try:
        with open(c_file, "r") as f:
            content = f.read()
        if not content.startswith(prefix):
            with open(c_file, "w") as f:
                f.write(spdx_header + content)
    except IOError as e:
        raise RuntimeError(f"Failed to write SPDX header for {c_file}: {e}")


# Remove existing .c file to allow cythonize to regenerate
if os.path.exists("apywire/wiring.c"):
    os.remove("apywire/wiring.c")

ext_modules = cythonize("apywire/wiring.py", force=True)

# Add SPDX header to the generated .c file
if os.path.exists("apywire/wiring.c"):
    add_spdx_header("apywire/wiring.c")

setup(ext_modules=ext_modules, python_requires=">=3.12")
