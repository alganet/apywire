<!--
SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>

SPDX-License-Identifier: ISC
-->

# Async Support

apywire provides built-in support for asynchronous object access via the `AioAccessor` pattern.

## Overview

The `AioAccessor` allows you to access wired objects in async contexts using `await`. This is useful when:

- Your application is built with `asyncio`
- You want to instantiate objects without blocking the event loop
- You're working with async frameworks like FastAPI, aiohttp, or Starlette

## Basic Async Access

Use the `.aio` attribute to get async accessors:

```python
import asyncio
from apywire import Wiring

spec = {
    "datetime.datetime now": {"year": 2025, "month": 1, "day": 1},
}

async def main():
    wired = Wiring(spec)

    # Async access
    dt = await wired.aio.now()
    print(dt)  # 2025-01-01 00:00:00

asyncio.run(main())
```

This is especially useful for [factory methods](advanced.md#factory-methods) that perform I/O operations.

## How It Works

When you use `.aio`, apywire wraps the object instantiation in an executor:

```python
# Under the hood (simplified)
async def aio_accessor():
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, sync_accessor)
```

This means:

1. Object instantiation runs in a thread pool executor
2. The async event loop is not blocked
3. The object is still cached after first instantiation

## Async vs Sync Access

### Sync Access

```python
wired = Wiring(spec)
obj = wired.my_object()  # Synchronous, blocks until instantiated
```

### Async Access

```python
async def get_object():
    wired = Wiring(spec)
    obj = await wired.aio.my_object()  # Async, doesn't block event loop
    return obj
```

## Caching with Async

Just like sync access, async access caches objects:

```python
async def main():
    wired = Wiring(spec)

    obj1 = await wired.aio.my_object()
    obj2 = await wired.aio.my_object()

    assert obj1 is obj2  # True - same cached instance!
```

You can even mix sync and async access - they share the same cache:

```python
async def main():
    wired = Wiring(spec)

    obj1 = wired.my_object()  # Sync access
    obj2 = await wired.aio.my_object()  # Async access

    assert obj1 is obj2  # True - same object!
```

## When to Use Async Access

### ✅ Use Async Access When:

- Working in async contexts (`async def` functions)
- Using async frameworks (FastAPI, aiohttp, etc.)
- Object instantiation might be slow and you don't want to block
- You want to instantiate multiple objects concurrently

### ❌ Don't Use Async Access When:

- Working in sync code (use regular accessors instead)
- Object instantiation is very fast (overhead not worth it)
- You don't have an event loop running

## Concurrent Instantiation

You can instantiate multiple objects concurrently:

```python
import asyncio
from apywire import Wiring

spec = {
    "MyDatabase db1": {"host": "server1.example.com"},
    "MyDatabase db2": {"host": "server2.example.com"},
    "MyDatabase db3": {"host": "server3.example.com"},
}

async def main():
    wired = Wiring(spec)

    # Instantiate all three databases concurrently
    db1, db2, db3 = await asyncio.gather(
        wired.aio.db1(),
        wired.aio.db2(),
        wired.aio.db3(),
    )

    print("All databases ready!")

asyncio.run(main())
```

## Real-World Example: FastAPI

```python
from fastapi import FastAPI, Depends
from apywire import Wiring

spec = {
    "database_url": "postgresql://localhost/mydb",
    "redis_url": "redis://localhost",

    "psycopg2.connect db": {"dsn": "{database_url}"},
    "redis.Redis cache": {"url": "{redis_url}"},
    "MyRepository repository": {"db": "{db}"},
}

# Create wiring container at startup
wired = Wiring(spec)

app = FastAPI()

async def get_repository():
    """Dependency that provides the repository."""
    return await wired.aio.repository()

@app.get("/users/{user_id}")
async def get_user(user_id: int, repo = Depends(get_repository)):
    """Get user by ID."""
    user = await repo.get_user(user_id)
    return user
```

## Compiling with Async Support

When compiling your wiring spec to code, you can include async support:

```python
from apywire import WiringCompiler

compiler = WiringCompiler(spec)
code = compiler.compile(aio=True)  # Include async accessors in generated code
```

The generated code will include both sync and async accessor methods.

## Thread Safety with Async

If you're using async access in a multi-threaded environment (e.g., running multiple event loops in different threads), enable thread safety:

```python
wired = Wiring(spec, thread_safe=True)

async def main():
    obj = await wired.aio.my_object()  # Thread-safe async access
```

See [Thread Safety](thread-safety.md) for more details.

## Performance Considerations

### Overhead

Async access has a small overhead due to executor scheduling:

```python
import time

spec = {
    "datetime.datetime dt": {"year": 2025, "month": 1, "day": 1},
}

wired = Wiring(spec)

# Sync access (very fast)
start = time.perf_counter()
_ = wired.dt()
sync_time = time.perf_counter() - start

# Async access (slightly slower due to executor)
async def async_test():
    start = time.perf_counter()
    _ = await wired.aio.dt()
    return time.perf_counter() - start

async_time = asyncio.run(async_test())

# async_time will be slightly higher than sync_time
```

For lightweight objects, the overhead might not be worth it. Use async access when:

- Object instantiation involves I/O (database connections, file opening, etc.)
- You need to instantiate multiple objects concurrently
- You're already in an async context and want consistency

### Caching Mitigates Overhead

Since objects are cached after first access, the overhead only applies to the first instantiation:

```python
async def main():
    wired = Wiring(spec)

    # First access: pays executor overhead
    obj1 = await wired.aio.my_object()

    # Subsequent accesses: instant, no overhead
    obj2 = await wired.aio.my_object()  # Cached!
```

## Error Handling

Async access raises the same exceptions as sync access; see [Circular dependencies](user-guide/circular-dependencies.md) for details on `CircularWiringError`.

```python
from apywire import UnknownPlaceholderError, CircularWiringError

async def main():
    spec = {
        "MyClass obj": {"dep": "{nonexistent}"},
    }

    wired = Wiring(spec)

    try:
        obj = await wired.aio.obj()
    except UnknownPlaceholderError as e:
        print(f"Error: {e}")
```

## Best Practices

### 1. Use Async Accessors in Async Contexts

```python
# Good
async def setup():
    wired = Wiring(spec)
    db = await wired.aio.database()

# Avoid - don't mix contexts unnecessarily
def setup():
    wired = Wiring(spec)
    db = asyncio.run(wired.aio.database())  # Awkward!
```

### 2. Instantiate Dependencies Concurrently

```python
# Good - concurrent
async def setup():
    wired = Wiring(spec)
    db, cache, logger = await asyncio.gather(
        wired.aio.database(),
        wired.aio.cache(),
        wired.aio.logger(),
    )

# Works but slower - sequential
async def setup():
    wired = Wiring(spec)
    db = await wired.aio.database()
    cache = await wired.aio.cache()
    logger = await wired.aio.logger()
```

### 3. Don't Over-Optimize

```python
# Overkill for lightweight objects
async def get_datetime():
    wired = Wiring({"datetime.datetime now": {"year": 2025, "month": 1, "day": 1}})
    dt = await wired.aio.now()  # Unnecessary async for simple object

# Just use sync access for lightweight objects
def get_datetime():
    wired = Wiring({"datetime.datetime now": {"year": 2025, "month": 1, "day": 1}})
    dt = wired.now()  # Better - no async overhead
```

## Next Steps

- **[Thread Safety](thread-safety.md)** - Combine async with thread safety
- **[Compilation](compilation.md)** - Generate async-capable code
- **[Basic Usage](basic-usage.md)** - Review sync accessor patterns
