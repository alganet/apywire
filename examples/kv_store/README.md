<!--
SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>

SPDX-License-Identifier: ISC
-->

# Key-Value Store Example

This example demonstrates how to wire **foreign objects** (classes from external packages) using `apywire`.

We instantiate `fakeredis.FakeRedis` directly from the configuration file, passing constructor arguments. This shows how `apywire` can act as a universal factory for any Python class, not just your own.

## Dependencies

This example requires `fakeredis` and `pyyaml`.

```bash
uv run --with fakeredis --with pyyaml --with apywire python main.py
```

## Running the Example

```bash
uv run --with fakeredis --with pyyaml --with apywire python main.py
```

Expected output:

```
Setting 'foo' to 'bar'...
Got 'foo': bar
```

## Swapping Implementations

To use a real Redis server, you would simply change the config to:

```yaml
redis.Redis redis:
  host: "localhost"
  port: 6379
  # ...
```

No code changes required!
