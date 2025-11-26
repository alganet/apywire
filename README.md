<!--
SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>

SPDX-License-Identifier: ISC
-->

# apywire

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: ISC](https://img.shields.io/badge/License-ISC-blue.svg)](https://opensource.org/licenses/ISC)

Lazy object wiring and dependency injection for Python 3.12+

## Features

- 🚀 Lazy Loading
- ⚡ Async Support
- 🔒 Thread Safety
- 📦 Code Generation
- 📄 Naturally Configurable
- 🎯 Zero Dependencies

## Installation

```bash
pip install apywire
```

## Quick Example

```python
from apywire import Wiring

spec = {
    "datetime.datetime now": {"year": 2025, "month": 1, "day": 1},
    "MyService service": {"start_time": "{now}"},  # Dependency injection
}

wired = Wiring(spec)
service = wired.service()  # Lazy instantiation + caching
```

## Documentation

📚 **[Full Documentation](docs/index.md)** • [Getting Started](docs/getting-started.md) • [API Reference](docs/api-reference.md) • [Examples](docs/examples.md)

Build docs locally:
```bash
make docs-serve  # http://127.0.0.1:8000
```

## Development

```bash
make .venv && source .venv/bin/activate  # Setup
make all                                  # Format, lint, test, build
```

See [AGENTS.md](AGENTS.md) for guidelines.

## License

ISC License - see [LICENSES/ISC.txt](LICENSES/ISC.txt)
