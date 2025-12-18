<!--
SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>

SPDX-License-Identifier: ISC
-->

# Command Line Interface

apywire provides a CLI for generating specs from class introspection and compiling specs to Python code.

## Installation

The CLI is included with apywire:

```bash
uv pip install apywire
```

Verify the installation:

```bash
python -m apywire --version
```

## Commands

### generate

Generate a wiring spec by introspecting class constructors.

```bash
python -m apywire generate --format FORMAT ENTRY [ENTRY ...]
```

**Arguments:**

- `--format FORMAT` - Output format: `ini`, `toml`, or `json` (required)
- `ENTRY` - One or more class entries as `module.Class name`

**Examples:**

```bash
# Generate a spec for datetime.datetime
python -m apywire generate --format json "datetime.datetime now"

# Generate TOML and save to file
python -m apywire generate --format toml "datetime.datetime now" > config.toml

# Multiple entries
python -m apywire generate --format json \
    "datetime.datetime now" \
    "collections.OrderedDict config"
```

**Output:**

The generator introspects the class constructor and creates placeholders for each parameter:

```bash
$ python -m apywire generate --format toml "datetime.datetime now"
```

```toml
["datetime.datetime now"]
year = "{now_year}"
month = "{now_month}"
day = "{now_day}"
...
```

### compile

Compile a spec file to Python code.

```bash
python -m apywire compile --format FORMAT [--aio] [--thread-safe] FILE
```

**Arguments:**

- `--format FORMAT` - Input format: `ini`, `toml`, or `json` (required)
- `--aio` - Generate async accessors using `run_in_executor`
- `--thread-safe` - Generate thread-safe accessors with locking
- `FILE` - Input spec file path, or `-` to read from stdin

**Examples:**

```bash
# Compile a JSON spec
python -m apywire compile --format json config.json

# Compile with async support
python -m apywire compile --format toml --aio config.toml > wiring.py

# Compile with thread safety
python -m apywire compile --format ini --thread-safe config.ini

# Read from stdin
cat config.json | python -m apywire compile --format json -
```

**Output:**

The compiler generates a Python module with a `Compiled` class:

```python
import datetime

class Compiled:

    def now(self):
        if not hasattr(self, '_now'):
            self._now = datetime.datetime(year=self.now_year(), ...)
        return self._now

    def now_year(self):
        return 2025

compiled = Compiled()
```

## Full Workflow

A typical workflow combines generate and compile:

### 1. Generate a Spec

```bash
python -m apywire generate --format toml "datetime.datetime now" > config.toml
```

### 2. Customize the Spec

Edit `config.toml` with your values:

```toml
now_year = 2025
now_month = 6
now_day = 15

["datetime.datetime now"]
year = "{now_year}"
month = "{now_month}"
day = "{now_day}"
```

### 3. Compile to Python

```bash
python -m apywire compile --format toml config.toml > wiring.py
```

### 4. Use in Your Application

```python
from wiring import compiled

dt = compiled.now()
print(f"Date: {dt}")  # Date: 2025-06-15 00:00:00
```

## Pipeline Usage

You can pipe generate output directly to compile:

```bash
# Generate and compile in one command
python -m apywire generate --format json "collections.OrderedDict cfg" \
    | python -m apywire compile --format json -
```

## Format Reference

### JSON

Direct mapping—no special handling needed:

```json
{
  "collections.OrderedDict config": {},
  "max_size": 100
}
```

### TOML

Top-level keys are constants, tables are wiring entries:

```toml
max_size = 100

["collections.OrderedDict config"]
```

!!! note "Quoted Section Names"
    TOML section names containing spaces must be quoted: `["module.Class name"]`

### INI

Uses `[constants]` section for constants (required by INI format):

```ini
[constants]
max_size = 100

[collections.OrderedDict config]
```

## Compiler Options

### --aio

Generates async accessors that use `asyncio.run_in_executor`:

```python
async def now(self):
    if not hasattr(self, '_now'):
        loop = asyncio.get_running_loop()
        self._now = await loop.run_in_executor(None, lambda: datetime.datetime(...))
    return self._now
```

### --thread-safe

Generates thread-safe accessors with locking:

```python
class Compiled(ThreadSafeMixin):

    def __init__(self):
        self._init_thread_safety()

    def now(self):
        if not hasattr(self, '_now'):
            self._now = self._instantiate_attr('now', lambda: datetime.datetime(...))
        return self._now
```

You can combine both flags:

```bash
python -m apywire compile --format json --aio --thread-safe config.json
```

## Next Steps

- **[Configuration Files](configuration-files.md)** - Loading specs from config files
- **[Compilation](compilation.md)** - Understanding the compiled output
- **[Generator](generator.md)** - Python API for the generator
