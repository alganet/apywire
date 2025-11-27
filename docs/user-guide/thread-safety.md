<!--
SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>

SPDX-License-Identifier: ISC
-->

# Thread Safety

apywire provides optional thread-safe instantiation for multi-threaded applications using optimistic locking.

## Overview

By default, `Wiring` containers are **not thread-safe**. This is intentional - thread safety has overhead, and many applications don't need it.

For multi-threaded applications, enable thread safety:

```python
from apywire import Wiring

wired = Wiring(spec, thread_safe=True)
```

## When to Enable Thread Safety

### ✅ Enable Thread Safety When:

- Running a multi-threaded web server (e.g., Gunicorn with multiple workers using threads)
- Sharing a `Wiring` container across multiple threads
- Instantiating objects from multiple concurrent threads

### ❌ Don't Enable Thread Safety When:

- Using async/await with a single event loop (use async, not threads)
- Single-threaded applications
- Each thread has its own `Wiring` container instance

Rule of thumb: If you're not sure if you need thread-safe containers, you probably
don't need them.

## How It Works

apywire uses a two-level locking strategy:

### 1. Optimistic Per-Attribute Locking

Each wired attribute has its own lock. When accessing an object:

1. Try to acquire the attribute-specific lock
2. If acquired, instantiate the object and cache it
3. Release the lock

This minimizes contention - different threads can instantiate different objects simultaneously.

```python
# Thread 1 accessing wired.db()
# Thread 2 accessing wired.cache()
# These can happen concurrently - different locks!
```

### 2. Global Fallback Locking

If a thread can't acquire an attribute lock (contention), it falls back to a global lock with retries:

1. Try to acquire the global lock
2. Retry with exponential backoff
3. If max retries exceeded, raise `LockUnavailableError`

This handles high-contention scenarios gracefully.

## Configuration Options

### max_lock_attempts

Maximum number of retry attempts when falling back to global lock:

```python
wired = Wiring(spec, thread_safe=True, max_lock_attempts=20)  # Default: 10
```

Higher values mean more retries before giving up, but longer potential waiting.

### lock_retry_sleep

Sleep duration (in seconds) between retry attempts:

```python
wired = Wiring(spec, thread_safe=True, lock_retry_sleep=0.005)  # Default: 0.01
```

Lower values mean faster retries, but more CPU usage. Higher values reduce CPU but increase latency.

## Basic Usage

```python
import threading
from apywire import Wiring

spec = {
    "datetime.datetime now": {"year": 2025, "month": 1, "day": 1},
}

wired = Wiring(spec, thread_safe=True)

def worker():
    dt = wired.now()  # Thread-safe access
    print(f"Thread {threading.current_thread().name}: {dt}")

# Create multiple threads
threads = [threading.Thread(target=worker) for _ in range(10)]

# Start all threads
for t in threads:
    t.start()

# Wait for completion
for t in threads:
    t.join()

# All threads get the same cached instance
```

## Error Handling

### LockUnavailableError

Raised when maximum lock retry attempts are exceeded:

```python
from apywire import LockUnavailableError

wired = Wiring(spec, thread_safe=True, max_lock_attempts=1)

try:
    obj = wired.my_object()
except LockUnavailableError as e:
    print(f"Could not acquire lock: {e}")
```

In practice, this is rare and usually indicates:

- Extremely high contention
- `max_lock_attempts` set too low
- A deadlock or very slow instantiation

## Performance Implications

Thread safety has overhead:

### Non-Thread-Safe (Faster)

```python
wired = Wiring(spec, thread_safe=False)  # Default
obj = wired.my_object()  # No locking overhead
```

### Thread-Safe (Slower)

```python
wired = Wiring(spec, thread_safe=True)
obj = wired.my_object()  # Lock acquisition/release overhead
```

The overhead is typically negligible, but for very high-frequency access patterns, it can add up.

### Caching Reduces Overhead

Objects are only instantiated once, so locking only happens on first access:

```python
wired = Wiring(spec, thread_safe=True)

# First access: pays locking overhead
obj1 = wired.my_object()

# Subsequent accesses: instant, no locking needed
obj2 = wired.my_object()  # Cached!
```

## Real-World Example: Multi-Threaded Web Server

```python
from concurrent.futures import ThreadPoolExecutor
from apywire import Wiring

spec = {
    "database_url": "postgresql://localhost/mydb",
    "psycopg2.pool.ThreadedConnectionPool pool": {
        "minconn": 1,
        "maxconn": 20,
        "dsn": "{database_url}",
    },
}

# Create thread-safe wiring container
wired = Wiring(spec, thread_safe=True)

def handle_request(request_id):
    """Simulate handling a web request."""
    # Each thread safely accesses the connection pool
    pool = wired.pool()
    conn = pool.getconn()

    # Use connection...
    print(f"Request {request_id} using connection")

    pool.putconn(conn)

# Simulate multiple concurrent requests
with ThreadPoolExecutor(max_workers=10) as executor:
    futures = [executor.submit(handle_request, i) for i in range(100)]
    for future in futures:
        future.result()
```

## Combining with Async

You can combine thread safety with async access:

```python
import asyncio
from apywire import Wiring

wired = Wiring(spec, thread_safe=True)

async def main():
    # Thread-safe async access
    obj = await wired.aio.my_object()
```

This is useful when:

- Running multiple event loops in different threads
- Mixing sync threaded code with async code

## Compiling with Thread Safety

Generate thread-safe compiled code:

```python
from apywire import WiringCompiler

compiler = WiringCompiler(spec)
code = compiler.compile(thread_safe=True)
```

The generated code will include the same two-level locking mechanism.

## Thread-Local State

apywire uses thread-local storage to track the resolution stack for circular dependency detection:

```python
# Under the hood
import threading

class _ThreadLocalState(threading.local):
    def __init__(self):
        self.resolving: list[str] = []
```

This ensures circular dependency detection works correctly across threads without interference.

## Testing Thread Safety

### Test for Race Conditions

```python
import threading
from apywire import Wiring

spec = {
    "MyCounter counter": {},
}

wired = Wiring(spec, thread_safe=True)

results = []

def worker():
    obj = wired.counter()
    results.append(id(obj))  # Store object id

threads = [threading.Thread(target=worker) for _ in range(100)]

for t in threads:
    t.start()
for t in threads:
    t.join()

# All threads should get the same object
assert len(set(results)) == 1, "Race condition detected!"
```

### Test for Deadlocks

```python
def test_no_deadlock():
    spec = {
        "MyClass obj": {},
    }

    wired = Wiring(spec, thread_safe=True, max_lock_attempts=5)

    def worker():
        for _ in range(100):
            _ = wired.obj()

    threads = [threading.Thread(target=worker) for _ in range(10)]

    for t in threads:
        t.start()
    for t in threads:
        t.join()  # Should complete without hanging
```

## Best Practices

### 1. Enable Thread Safety Only When Needed

```python
# Development (single-threaded)
wired = Wiring(spec, thread_safe=False)

# Production (multi-threaded)
import os
thread_safe = os.getenv("MULTI_THREADED", "false") == "true"
wired = Wiring(spec, thread_safe=thread_safe)
```

### 2. Test with Realistic Concurrency

```python
# Test with actual thread count you'll use in production
from concurrent.futures import ThreadPoolExecutor

def test_with_realistic_concurrency():
    wired = Wiring(spec, thread_safe=True)

    with ThreadPoolExecutor(max_workers=20) as executor:  # Match prod
        futures = [executor.submit(wired.my_object) for _ in range(1000)]
        for future in futures:
            future.result()
```

### 3. Tune Lock Parameters for Your Use Case

```python
# High contention: increase retries
wired = Wiring(spec, thread_safe=True, max_lock_attempts=50)

# Low contention: decrease sleep time
wired = Wiring(spec, thread_safe=True, lock_retry_sleep=0.001)
```

### 4. Monitor for LockUnavailableError

```python
import logging

logger = logging.getLogger(__name__)

try:
    obj = wired.my_object()
except LockUnavailableError:
    logger.error("Lock contention too high - consider increasing max_lock_attempts")
    raise
```

## Advanced: Understanding the Lock Mechanism

The locking implementation uses:

1. **Per-attribute locks**: `dict[str, threading.Lock]` - one lock per wired attribute
2. **Global lock**: Single `threading.Lock` for fallback
3. **Thread-local state**: `threading.local()` for circular dependency tracking

```python
# Simplified pseudocode
def __getattr__(self, name: str):
    if name in self._values:
        return self._values[name]  # Already cached

    # Try optimistic lock
    attr_lock = self._attr_locks.get(name)
    if attr_lock.acquire(blocking=False):
        try:
            obj = self._instantiate(name)
            self._values[name] = obj
            return obj
        finally:
            attr_lock.release()

    # Fall back to global lock with retries
    for attempt in range(self._max_lock_attempts):
        if self._global_lock.acquire(blocking=False):
            try:
                obj = self._instantiate(name)
                self._values[name] = obj
                return obj
            finally:
                self._global_lock.release()
        time.sleep(self._lock_retry_sleep)

    raise LockUnavailableError(f"Could not acquire lock for {name}")
```

## Next Steps

- **[Basic Usage](basic-usage.md)** - Learn about non-thread-safe usage
- **[Async Support](async-support.md)** - Combine with async patterns
- **[Compilation](compilation.md)** - Generate thread-safe compiled code
