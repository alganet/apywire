<!--
SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>

SPDX-License-Identifier: ISC
-->

# apywire

[![PyPI version](https://img.shields.io/pypi/v/apywire.svg)](https://pypi.org/project/apywire/)
[![Python versions](https://img.shields.io/pypi/pyversions/apywire.svg)](https://pypi.org/project/apywire/)
[![License](https://img.shields.io/pypi/l/apywire.svg)](https://github.com/alganet/apywire/blob/main/LICENSE)
[![CI](https://github.com/alganet/apywire/actions/workflows/ci.yml/badge.svg)](https://github.com/alganet/apywire/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-latest-blue.svg)](https://alganet.github.io/apywire/)

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

`spec` is a plain dictionary. It can be written in Python, or come from a
[config file](docs/user-guide/configuration-files.md), apywire doesn't care.

## Documentation

📚 **[Full Documentation](docs/index.md)** • [Getting Started](docs/getting-started.md) • [API Reference](docs/api-reference.md) • [Examples](docs/examples.md)

Build docs locally:
```bash
make docs-serve  # http://127.0.0.1:8000
```

## Development

```bash
make .venv && source .venv/bin/activate  # Setup
make all                                 # Format, lint, test, build
```

See [docs/development.md](docs/development.md) for guidelines.

## License

ISC License - see [LICENSES/ISC.txt](LICENSES/ISC.txt)
