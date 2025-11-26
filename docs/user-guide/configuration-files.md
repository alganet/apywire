<!--
SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>

SPDX-License-Identifier: ISC
-->

# Configuration Files

Since apywire specs are just Python dictionaries, you can load them from any configuration file format: YAML, TOML, JSON, INI, or any other format that converts to Python data structures.

## Why Use Configuration Files?

- **Separation of Concerns**: Keep configuration separate from code
- **Environment-Specific**: Different configs for dev, staging, production
- **Version Control**: Track configuration changes
- **Non-Developers**: Allow non-programmers to modify configuration
- **Validation**: Use schema validation tools for your config format

## YAML

YAML is readable and supports complex nested structures.

### Example: `config.yaml`

```yaml
# Database configuration
database_url: postgresql://localhost/mydb
pool_min: 1
pool_max: 20

# Database connection pool
psycopg2.pool.ThreadedConnectionPool pool:
  minconn: "{pool_min}"
  maxconn: "{pool_max}"
  dsn: "{database_url}"

# Redis cache
redis_url: redis://localhost:6379
redis.Redis cache:
  url: "{redis_url}"

# Application service
MyService service:
  db: "{pool}"
  cache: "{cache}"
  debug: true
```

### Loading YAML

```python
import yaml
from apywire import Wiring

# Load spec from YAML file
with open("config.yaml", "r") as f:
    spec = yaml.safe_load(f)

wired = Wiring(spec, thread_safe=True)
service = wired.service()
```

### YAML Benefits

- ✅ Very human-readable
- ✅ Supports comments
- ✅ Native support for lists, dicts, booleans
- ✅ Multi-line strings
- ❌ Requires `pyyaml` package

## TOML

TOML is Python-friendly and great for structured configuration.

### Example: `config.toml`

```toml
# Database configuration
database_url = "postgresql://localhost/mydb"
pool_min = 1
pool_max = 20

# Redis
redis_url = "redis://localhost:6379"

# Database connection pool
["psycopg2.pool.ThreadedConnectionPool pool"]
minconn = "{pool_min}"
maxconn = "{pool_max}"
dsn = "{database_url}"

# Redis cache
["redis.Redis cache"]
url = "{redis_url}"

# Application service
["MyService service"]
db = "{pool}"
cache = "{cache}"
debug = true
```

!!! note "TOML Section Names with Spaces"
    TOML section names with spaces must be quoted: `["module.Class name"]`

### Loading TOML

```python
import tomllib  # Python 3.11+, or use 'tomli' package
from apywire import Wiring

# Load TOML file
with open("config.toml", "rb") as f:
    spec = tomllib.load(f)

# Use directly - TOML structure matches apywire spec format!
wired = Wiring(spec)
```

### TOML Benefits

- ✅ Built into Python 3.11+ (`tomllib`)
- ✅ Type-safe (strict types)
- ✅ Supports comments
- ✅ Good for structured data
- ✅ Dots in section names work perfectly
- ✅ No conversion needed!

## JSON

JSON is universal and works everywhere.

### Example: `config.json`

```json
{
  "database_url": "postgresql://localhost/mydb",
  "pool_min": 1,
  "pool_max": 20,
  "redis_url": "redis://localhost:6379",

  "psycopg2.pool.ThreadedConnectionPool pool": {
    "minconn": "{pool_min}",
    "maxconn": "{pool_max}",
    "dsn": "{database_url}"
  },

  "redis.Redis cache": {
    "url": "{redis_url}"
  },

  "MyService service": {
    "db": "{pool}",
    "cache": "{cache}",
    "debug": true
  }
}
```

### Loading JSON

```python
import json
from apywire import Wiring

# Load spec from JSON file
with open("config.json", "r") as f:
    spec = json.load(f)

wired = Wiring(spec)
service = wired.service()
```

### JSON Benefits

- ✅ Built into Python standard library
- ✅ Universal format
- ✅ Easy to generate programmatically
- ✅ Works with REST APIs
- ❌ No comments
- ❌ Verbose syntax

## INI/CFG

INI files are simple and widely used for configuration.

### Example: `config.ini`

```ini
[constants]
database_url = postgresql://localhost/mydb
pool_min = 1
pool_max = 20
redis_url = redis://localhost:6379

[psycopg2.pool.ThreadedConnectionPool pool]
minconn = {pool_min}
maxconn = {pool_max}
dsn = {database_url}

[redis.Redis cache]
url = {redis_url}

[MyService service]
db = {pool}
cache = {cache}
debug = true
```

### Loading INI

```python
import configparser
from apywire import Wiring

# Load INI file
config = configparser.ConfigParser()
config.read("config.ini")

# Convert to apywire spec
spec = {}
for section in config.sections():
    if section == "constants":
        # Constants go in top level
        for key, value in config[section].items():
            # Type conversion (INI reads everything as strings)
            if value.isdigit():
                spec[key] = int(value)
            elif value.lower() in ("true", "false"):
                spec[key] = value.lower() == "true"
            else:
                spec[key] = value
    else:
        # Wired objects
        spec[section] = dict(config[section])

wired = Wiring(spec)
```

### INI Benefits

- ✅ Built into Python standard library
- ✅ Simple syntax
- ✅ Widely understood
- ✅ Supports comments
- ❌ All values are strings (need type conversion)
- ❌ Limited nesting

## Placeholder Expansion

Constants can now reference other constants and wired objects using placeholder syntax `{name}`.

### Constant → Constant (Immediate Expansion)

When a constant references only other constants, it's expanded immediately at initialization:

```yaml
# config.yaml
host: localhost
port: 5432
database_name: myapp

# This is expanded immediately
database_url: "postgresql://{host}:{port}/{database_name}"
```

```python
import yaml
from apywire import Wiring

with open("config.yaml") as f:
    spec = yaml.safe_load(f)

wired = Wiring(spec)

# The database_url constant is already expanded to the full connection string
```

**Nested references work too:**

```yaml
base_url: http://api.example.com
v1_url: "{base_url}/v1"
users_endpoint: "{v1_url}/users"  # Becomes "http://api.example.com/v1/users"
```

### Constant → Wired Object (Auto-Promoted)

When a constant references a wired object, it's automatically promoted to an accessor with lazy evaluation:

```yaml
database_url: "postgresql://localhost/mydb"

psycopg2.connect conn:
  dsn: "{database_url}"

# This references a wired object, so it becomes an accessor
status: "Connected to {conn}"
```

```python
wired = Wiring(spec)

# status is now an accessor (not in _values)
# It lazily instantiates conn and converts it to string
status_msg = wired.status()  # "Connected to <connection object>"
```

### Mixed References

Constants with both constant and wired object references are auto-promoted:

```yaml
host: localhost

datetime.datetime server_start:
  year: 2025
  month: 1
  day: 1

# This has both constant and wired refs, so it's auto-promoted
status: "Server {host} started at {server_start}"
```

```python
wired = Wiring(spec)

# Use constants via placeholders in other wired objects
msg = wired.status()  # "Server localhost started at 2025-01-01 00:00:00"
```

### Benefits

- ✅ **DRY Configuration**: Define values once, reference everywhere
- ✅ **Computed Constants**: Build strings from multiple parts
- ✅ **Flexible**: Mix constants and wired objects
- ✅ **Lazy Evaluation**: Wired objects only instantiated when needed
- ✅ **Type Conversion**: Non-string constants automatically converted to strings

### Circular Dependencies

Circular references in constants are detected at initialization:

```yaml
a: "{b}"
b: "{a}"  # ❌ CircularWiringError
```

Circular references with wired objects follow normal lazy detection:

```yaml
MyClass obj_a:
  dep: "{obj_b}"

MyClass obj_b:
  dep: "{obj_a}"  # ❌ CircularWiringError when accessed
```

## Environment-Based Configuration

Load different configs based on environment:

```python
import os
import yaml
from apywire import Wiring

# Determine environment
env = os.getenv("APP_ENV", "dev")

# Load appropriate config file
config_file = f"config.{env}.yaml"
with open(config_file, "r") as f:
    spec = yaml.safe_load(f)

wired = Wiring(spec, thread_safe=(env == "production"))
```

File structure:
```
config.dev.yaml
config.staging.yaml
config.production.yaml
```

## Environment Variables in Configs

Mix configuration files with environment variables:

### YAML with Environment Variables

```yaml
# config.yaml
database_url: ${DATABASE_URL}
api_key: ${API_KEY}

MyService service:
  db_url: "{database_url}"
  api_key: "{api_key}"
```

### Loading with Substitution

```python
import os
import yaml
import re
from apywire import Wiring

def substitute_env_vars(config):
    """Recursively substitute ${VAR} with environment variables."""
    if isinstance(config, dict):
        return {k: substitute_env_vars(v) for k, v in config.items()}
    elif isinstance(config, list):
        return [substitute_env_vars(item) for item in config]
    elif isinstance(config, str):
        # Replace ${VAR} with environment variable
        pattern = r'\$\{([^}]+)\}'
        return re.sub(pattern, lambda m: os.getenv(m.group(1), ''), config)
    return config

# Load and substitute
with open("config.yaml", "r") as f:
    raw_spec = yaml.safe_load(f)

spec = substitute_env_vars(raw_spec)
wired = Wiring(spec)
```

## Schema Validation

Validate your configuration files before loading:

### YAML with Schema (using pydantic)

```python
from pydantic import BaseModel, Field
import yaml
from apywire import Wiring

class DatabaseConfig(BaseModel):
    database_url: str
    pool_min: int = Field(ge=1)
    pool_max: int = Field(ge=1, le=100)

class AppConfig(BaseModel):
    database: DatabaseConfig
    redis_url: str
    debug: bool = False

# Load and validate
with open("config.yaml", "r") as f:
    raw_config = yaml.safe_load(f)

# Validate structure
validated = AppConfig(**raw_config)

# Build apywire spec from validated config
spec = {
    "database_url": validated.database.database_url,
    "pool_min": validated.database.pool_min,
    "pool_max": validated.database.pool_max,
    # ... rest of spec
}

wired = Wiring(spec)
```

## Best Practices

### 1. Keep Secrets Out of Config Files

```python
# ❌ Bad: Secrets in config file
database_url: postgresql://user:password@localhost/db

# ✅ Good: Reference environment variables
database_url: ${DATABASE_URL}
```

### 2. Use Separate Configs Per Environment

```
config/
├── base.yaml          # Shared configuration
├── dev.yaml           # Development overrides
├── staging.yaml       # Staging overrides
└── production.yaml    # Production overrides
```

### 3. Document Your Config Format

Add a `config.example.yaml` to your repository:

```yaml
# config.example.yaml
# Copy this to config.yaml and customize

database_url: postgresql://localhost/mydb  # Database connection string
pool_min: 1                                 # Minimum pool connections
pool_max: 20                                # Maximum pool connections
```

### 4. Validate Before Loading

Always validate configuration before passing to Wiring:

```python
def load_config(filename):
    """Load and validate configuration."""
    with open(filename) as f:
        spec = yaml.safe_load(f)

    # Validate required keys
    required = ["database_url", "redis_url"]
    for key in required:
        if key not in spec:
            raise ValueError(f"Missing required config: {key}")

    return spec

spec = load_config("config.yaml")
wired = Wiring(spec)
```

## Complete Example

Putting it all together with best practices:

### Project Structure

```
myapp/
├── config/
│   ├── base.yaml
│   ├── dev.yaml
│   ├── production.yaml
│   └── config.example.yaml
├── app/
│   ├── __init__.py
│   ├── config.py
│   └── main.py
└── .env.example
```

### `app/config.py`

```python
import os
import yaml
from pathlib import Path
from apywire import Wiring

def load_spec(env: str = None) -> dict:
    """Load wiring spec from YAML configuration."""
    if env is None:
        env = os.getenv("APP_ENV", "dev")

    config_dir = Path(__file__).parent.parent / "config"

    # Load base config
    with open(config_dir / "base.yaml") as f:
        spec = yaml.safe_load(f)

    # Load environment-specific overrides
    env_file = config_dir / f"{env}.yaml"
    if env_file.exists():
        with open(env_file) as f:
            env_spec = yaml.safe_load(f)
            spec.update(env_spec)

    # Substitute environment variables
    spec = substitute_env_vars(spec)

    return spec

def get_wired(env: str = None) -> Wiring:
    """Get configured Wiring instance."""
    spec = load_spec(env)
    thread_safe = env == "production"
    return Wiring(spec, thread_safe=thread_safe)
```

### `app/main.py`

```python
from app.config import get_wired

def main():
    wired = get_wired()

    # Access configured services
    db = wired.database()
    cache = wired.cache()
    service = wired.service()

    # Run application
    service.run()

if __name__ == "__main__":
    main()
```

## Next Steps

- **[Basic Usage](basic-usage.md)** - Learn the fundamentals
- **[Advanced Features](advanced.md)** - Complex patterns
- **[Examples](../examples.md)** - Real-world use cases
