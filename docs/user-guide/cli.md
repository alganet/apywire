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
python -m apywire compile --format FORMAT [--aio] [--thread-safe] [--emit-spec] FILE
```

**Arguments:**

- `--format FORMAT` - Input format: `ini`, `toml`, or `json` (required)
- `--aio` - Generate async accessors using `run_in_executor`
- `--thread-safe` - Generate thread-safe accessors with locking
- `--emit-spec` - Also emit the source spec as a module-level dict
- `FILE` - Input spec file path, or `-` to read from stdin

**Examples:**

```bash
# Compile a JSON spec
python -m apywire compile --format json config.json

# Compile with async support
python -m apywire compile --format toml --aio config.toml > wiring.py

# Compile with thread safety
python -m apywire compile --format ini --thread-safe config.ini

# Compile defaults that a user's config can later extend
python -m apywire compile --format toml --emit-spec defaults.toml > _defaults.py

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

### merge

Overlay spec files and print the effective spec — what a config *actually*
merges to. See [Merging Specs](merging.md) for the semantics.

```bash
python -m apywire merge --format FORMAT [--output-format FORMAT] SOURCE [SOURCE ...]
```

**Arguments:**

- `--format FORMAT` - Input format: `ini`, `toml`, or `json` (required)
- `--output-format FORMAT` - Output format (defaults to the input format)
- `SOURCE` - Specs in overlay order. Each is a file path, `-` for stdin, or
  an importable `pkg.module:name`

**Examples:**

```bash
# What does my config actually change?
python -m apywire merge --format toml defaults.toml user.toml

# Overlay a user's config onto compiled defaults (see --emit-spec)
python -m apywire merge --format toml myapp._defaults:spec user.toml

# Merge TOML, read the result as JSON
python -m apywire merge --format toml --output-format json base.toml user.toml
```

The `pkg.module:name` form is what pairs with `--emit-spec`: a compiled
container exposes its source spec as a module attribute, and that is the
base a user's config is overlaid onto.

TOML output requires `tomli_w`; without it, use `--output-format json`.

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

Adds async support via a `.aio` cached property (`CompiledAio` wrapper). All methods remain sync `def`; async access is provided through `compiled.aio.name()`:

```python
from functools import cached_property
from apywire.runtime import CompiledAio

class Compiled:
    def now(self):
        if not hasattr(self, '_now'):
            self._now = datetime.datetime(...)
        return self._now

    @cached_property
    def aio(self):
        return CompiledAio(self)
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

### --emit-spec

Also emits the source spec as a module-level dict, so the compiled
module is self-describing:

```python
import datetime
spec = {'y': 2025, 'datetime.date d': {'year': '{y}', 'month': 1, 'day': 1}}

class Compiled:

    def d(self):
        if not hasattr(self, '_d'):
            self._d = datetime.date(year=self.y(), month=1, day=1)
        return self._d

    def y(self):
        return 2025
compiled = Compiled()
```

Placeholders are emitted verbatim (`'{y}'` stays a string), so the spec
can be overlaid with [`merge_specs`](merging.md) and wired again — which
is how compiled defaults stay extensible by a user's config.

A spec that cannot be emitted — one holding a value with no literal
source representation, or one wiring a module whose root package is named
`spec` (the emitted assignment would shadow its import) — prints
`Error compiling spec: …` and exits 1.

## Next Steps

- **[Configuration Files](configuration-files.md)** - Loading specs from config files
- **[Merging Specs](merging.md)** - Overlaying one spec on another
- **[Compilation](compilation.md)** - Understanding the compiled output
- **[Generator](generator.md)** - Python API for the generator
