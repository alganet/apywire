<!--
SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>

SPDX-License-Identifier: ISC
-->

# Configuration Files

apywire supports loading specs from JSON, TOML, and INI configuration files. The `apywire.formats` module provides utilities for parsing and serializing specs in these formats.

## Why Use Configuration Files?

- **Separation of Concerns**: Keep configuration separate from code
- **Environment-Specific**: Different configs for dev, staging, production
- **Version Control**: Track configuration changes
- **Non-Developers**: Allow non-programmers to modify configuration
- **CLI Workflow**: Generate specs with CLI, edit, then compile

## Quick Start with CLI

The fastest way to create a configuration file is using the CLI:

```bash
# Generate a spec from class introspection
python -m apywire generate --format toml "datetime.datetime now" > config.toml

# Edit config.toml to customize values, then compile
python -m apywire compile --format toml config.toml > wiring.py
```

See [Command Line Interface](cli.md) for full CLI documentation.

## Supported Formats

### JSON

JSON provides direct mapping with no conversion needed.

**Example: `config.json`**

```json
{
  "database_url": "postgresql://localhost/mydb",
  "pool_size": 20,

  "myapp.Database db": {
    "url": "{database_url}",
    "pool_size": "{pool_size}"
  }
}
```

**Loading:**

```python
from apywire import Wiring
from apywire.formats import json_to_spec

with open("config.json") as f:
    spec = json_to_spec(f.read())

wired = Wiring(spec)
db = wired.db()
```

**Benefits:**

- ✅ Built into Python standard library
- ✅ Universal format
- ✅ No conversion needed
- ❌ No comments

### TOML

TOML is Python-friendly with top-level keys as constants and tables as wiring entries.

**Example: `config.toml`**

```toml
# Constants as top-level keys
database_url = "postgresql://localhost/mydb"
pool_size = 20

# Wiring entries as tables (quote names with spaces)
["myapp.Database db"]
url = "{database_url}"
pool_size = "{pool_size}"
```

!!! note "Quoted Section Names"
    TOML section names with spaces must be quoted: `["module.Class name"]`

**Loading:**

```python
from apywire import Wiring
from apywire.formats import toml_to_spec

with open("config.toml") as f:
    spec = toml_to_spec(f.read())

wired = Wiring(spec)
```

**Benefits:**

- ✅ Built into Python 3.11+ (`tomllib`)
- ✅ Supports comments
- ✅ Type-safe (integers, booleans, etc.)
- ✅ Clean syntax for nested structures

### INI

INI uses a `[constants]` section for constants (required by the format).

**Example: `config.ini`**

```ini
[constants]
database_url = postgresql://localhost/mydb
pool_size = 20

[myapp.Database db]
url = {database_url}
pool_size = {pool_size}
```

**Loading:**

```python
from apywire import Wiring
from apywire.formats import ini_to_spec

with open("config.ini") as f:
    spec = ini_to_spec(f.read())

wired = Wiring(spec)
```

**Benefits:**

- ✅ Built into Python standard library
- ✅ Simple syntax
- ✅ Supports comments
- ❌ All values are strings (automatic type conversion provided)

### YAML

YAML is not directly supported by the formats module, but you can use PyYAML:

```python
import yaml
from apywire import Wiring

with open("config.yaml") as f:
    spec = yaml.safe_load(f)

wired = Wiring(spec)
```

## Format Conversion

The formats module provides functions to convert between formats:

```python
from apywire.formats import (
    json_to_spec, spec_to_json,
    toml_to_spec, spec_to_toml,
    ini_to_spec, spec_to_ini,
)

# Load from one format
with open("config.json") as f:
    spec = json_to_spec(f.read())

# Save to another format
toml_output = spec_to_toml(spec)
with open("config.toml", "w") as f:
    f.write(toml_output)
```

## Placeholder Expansion

Constants can reference other constants and wired objects using `{name}` syntax.

### Constant → Constant

When a constant references only other constants, it's expanded immediately:

```toml
host = "localhost"
port = 5432
database_url = "postgresql://{host}:{port}/mydb"
```

### Constant → Wired Object

When a constant references a wired object, it becomes a lazy accessor:

```toml
["datetime.datetime server_start"]
year = 2025
month = 1
day = 1

# This is auto-promoted to an accessor
status = "Server started at {server_start}"
```

```python
wired = Wiring(spec)
msg = wired.status()  # "Server started at 2025-01-01 00:00:00"
```

## Environment-Based Configuration

Load different configs based on environment:

```python
import os
from apywire import Wiring
from apywire.formats import toml_to_spec

env = os.getenv("APP_ENV", "dev")
config_file = f"config.{env}.toml"

with open(config_file) as f:
    spec = toml_to_spec(f.read())

wired = Wiring(spec, thread_safe=(env == "production"))
```

## Environment Variables

You can substitute environment variables before parsing:

```python
import os
import re
from apywire import Wiring
from apywire.formats import toml_to_spec

def substitute_env(content: str) -> str:
    """Replace ${VAR} with environment variable values."""
    return re.sub(
        r'\$\{([^}]+)\}',
        lambda m: os.getenv(m.group(1), ''),
        content
    )

with open("config.toml") as f:
    content = substitute_env(f.read())
    spec = toml_to_spec(content)

wired = Wiring(spec)
```

## Complete Example

### Project Structure

```
myapp/
├── config/
│   ├── dev.toml
│   ├── production.toml
│   └── config.example.toml
├── app/
│   ├── __init__.py
│   ├── config.py
│   └── main.py
└── wiring.py  # Generated via CLI
```

### `config/dev.toml`

```toml
debug = true
database_url = "postgresql://localhost/myapp_dev"
pool_size = 5

["myapp.Database db"]
url = "{database_url}"
pool_size = "{pool_size}"

["myapp.Cache cache"]
backend = "memory"
```

### `app/config.py`

```python
import os
from pathlib import Path
from apywire import Wiring
from apywire.formats import toml_to_spec

def load_wiring() -> Wiring:
    env = os.getenv("APP_ENV", "dev")
    config_dir = Path(__file__).parent.parent / "config"
    config_file = config_dir / f"{env}.toml"

    with open(config_file) as f:
        spec = toml_to_spec(f.read())

    return Wiring(spec, thread_safe=(env == "production"))
```

### `app/main.py`

```python
from app.config import load_wiring

def main():
    wired = load_wiring()
    db = wired.db()
    cache = wired.cache()
    # Use services...

if __name__ == "__main__":
    main()
```

## Best Practices

1. **Keep Secrets Out**: Use environment variables for passwords and API keys
2. **Separate Configs**: Use different files for dev/staging/production
3. **Document Your Config**: Include a `config.example.toml` in version control
4. **Validate Early**: Check required keys before creating Wiring instance

## Next Steps

- **[Command Line Interface](cli.md)** - Generate and compile specs
- **[Basic Usage](basic-usage.md)** - Learn the fundamentals
- **[Compilation](compilation.md)** - Understanding compiled output
