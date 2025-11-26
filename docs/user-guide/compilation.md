<!--
SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>

SPDX-License-Identifier: ISC
-->

# Compilation

apywire can generate standalone Python code from your wiring spec using the `WiringCompiler` class and its `compile()` method. This is useful for production deployments and performance optimization.

## Overview

The `compile()` method generates Python code that behaves identically to the runtime `Wiring` container:

```python
from apywire import WiringCompiler

spec = {
    "datetime.datetime now": {"year": 2025, "month": 1, "day": 1},
}

compiler = WiringCompiler(spec)
code = compiler.compile()
print(code)
```

This generates a Python class with the same lazy loading, caching, and dependency resolution behavior.

## Basic Compilation

```python
from apywire import WiringCompiler

spec = {
    "datetime.datetime start": {"year": 2025, "month": 1, "day": 1},
    "datetime.timedelta delta": {"days": 7},
}

compiler = WiringCompiler(spec)
code = compiler.compile()

# Save to file
with open("compiled_wiring.py", "w") as f:
    f.write(code)
```

The generated code can be imported and used like the runtime container:

```python
from compiled_wiring import Compiled

wired = Compiled()
start = wired.start()
delta = wired.delta()
```

## Compilation Options

### aio (Async Support)

Include async accessors in the generated code:

```python
code = compiler.compile(aio=True)
```

Generated code will support both sync and async access:

```python
from compiled_wiring import Compiled

wired = Compiled()

# Sync access
obj = wired.my_object()

# Async access
import asyncio
obj = asyncio.run(wired.aio.my_object())
```

### thread_safe (Thread Safety)

Include thread-safe instantiation in the generated code:

```python
code = compiler.compile(thread_safe=True)
```

Generated code will use the same optimistic locking mechanism as runtime `Wiring`.

### Combined Options

```python
code = compiler.compile(aio=True, thread_safe=True)
```

Generates code with both async support and thread safety.

## Generated Code Structure

The compiled code contains:

### 1. Imports

All necessary imports for the wired classes:

```python
import datetime
import pathlib
# ... other imports
```

### 2. The Compiled Class

A class that mirrors your wiring spec:

```python
class Compiled:
    def __init__(self):
        self._values = {}
        # Thread-safe: locks initialization
        # Constants initialization
```

### 3. Accessor Methods

Methods for each wired object:

```python
def start(self):
    if "start" not in self._values:
        # Instantiation logic
        self._values["start"] = datetime.datetime(year=2025, month=1, day=1)
    return self._values["start"]
```

### 4. Async Accessors (if aio=True)

Async versions of accessor methods:

```python
class AioAccessors:
    async def start(self):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: self._wired.start())

@property
def aio(self):
    return self._aio_accessors
```

### 5. Thread Safety (if thread_safe=True)

Locking mechanisms and thread-local state.

## Why Compile?

### Benefits

1. **Performance**: Slightly faster than runtime `Wiring` (no dynamic `__getattr__` lookup)
2. **Deployment**: No need to include spec dictionary in production code
3. **Type Checking**: Generated code can be type-checked by mypy
4. **Inspection**: Easier to understand dependency graph by reading generated code
5. **Cython**: Can be compiled with Cython for additional performance

### Trade-offs

1. **Static**: Can't modify spec at runtime
2. **Code Size**: Generated code can be large for complex specs
3. **Maintenance**: Need to regenerate if spec changes

## Cython Compilation

apywire itself uses Cython for performance. You can compile the generated code with Cython:

### Step 1: Generate Python Code

```python
compiler = WiringCompiler(spec)
code = compiler.compile()
with open("wiring.py", "w") as f:
    f.write(code)
```

### Step 2: Create setup.py

```python
from setuptools import setup
from Cython.Build import cythonize

setup(
    ext_modules=cythonize("wiring.py"),
)
```

### Step 3: Build

```bash
python setup.py build_ext --inplace
```

This generates `wiring.c` and `wiring.so` (compiled extension).

## Real-World Example

### Development: Use Runtime Wiring

```python
# config.py
from apywire import Wiring

def get_spec():
    return {
        "database_url": "postgresql://localhost/mydb",
        "psycopg2.connect db": {"dsn": "{database_url}"},
        "MyRepository repo": {"db": "{db}"},
    }

wired = Wiring(get_spec())
```

### Production: Use Compiled Code

```python
# generate_wiring.py
from apywire import WiringCompiler
from config import get_spec

compiler = WiringCompiler(get_spec())
code = compiler.compile(aio=True, thread_safe=True)

with open("compiled_wiring.py", "w") as f:
    f.write(code)

print("Compiled wiring generated!")
```

Run once during deployment:

```bash
python generate_wiring.py
```

Use in production:

```python
# app.py
from compiled_wiring import Compiled

wired = Compiled()
repo = wired.repo()
```

## Inspecting Generated Code

The generated code is readable Python. You can inspect it to understand dependencies:

```python
spec = {
    "MyDatabase db": {},
    "MyCache cache": {"db": "{db}"},
    "MyService service": {"cache": "{cache}"},
}

compiler = WiringCompiler(spec)
code = compiler.compile()

# Save and inspect
with open("wiring.py", "w") as f:
    f.write(code)

# Look at wiring.py to see:
# - service() method calls cache()
# - cache() method calls db()
# - Dependency chain is explicit
```

## Licensing and Headers

The generated code doesn't include SPDX headers by default. Add them manually if needed:

```python
header = """# SPDX-FileCopyrightText: 2025 Your Name <your@email.com>
#
# SPDX-License-Identifier: ISC

"""

compiler = WiringCompiler(spec)
code = compiler.compile()
full_code = header + code

with open("wiring.py", "w") as f:
    f.write(full_code)
```

## Testing Compiled Code

Test that compiled code behaves identically to runtime:

```python
from apywire import Wiring

spec = {
    "datetime.datetime now": {"year": 2025, "month": 1, "day": 1},
}

# Runtime
wired_runtime = Wiring(spec)

# Compiled
compiler = WiringCompiler(spec)
code = compiler.compile()
exec(code)  # Defines Compiled class
wired_compiled = Compiled()

# Both should produce same results
assert wired_runtime.now() == wired_compiled.now()
```

## Best Practices

### 1. Generate During Build/Deploy

```bash
# In your CI/CD pipeline
python scripts/generate_wiring.py
python setup.py build_ext --inplace  # Optional: Cython compile
```

### 2. Version Control Generated Code

**Option A**: Don't commit generated code (regenerate on deploy)

```gitignore
# .gitignore
compiled_wiring.py
```

**Option B**: Commit generated code (easier for others to use)

Pros: Others can use without regenerating
Cons: Diffs in PRs, risk of forgetting to regenerate

### 3. Validate Generated Code

```python
# In your tests
def test_compiled_code_valid():
    from apywire import WiringCompiler

    compiler = WiringCompiler(spec)
    code = compiler.compile()

    # Check code compiles
    compile(code, "wiring.py", "exec")

    # Check code executes
    exec(code)
```

### 4. Use Same Options as Runtime

If you use `thread_safe=True` in runtime, compile with it too:

```python
# Development
wired = Wiring(spec, thread_safe=True)

# Production
compiler = WiringCompiler(spec)
code = compiler.compile(thread_safe=True)  # Match!
```

## Debugging Generated Code

If generated code has issues:

### 1. Save to File and Inspect

```python
code = compiler.compile()
with open("debug_wiring.py", "w") as f:
    f.write(code)

# Open debug_wiring.py in your editor
```

### 2. Check for Syntax Errors

```python
try:
    compile(code, "wiring.py", "exec")
except SyntaxError as e:
    print(f"Syntax error in generated code: {e}")
```

### 3. Test Imports

Make sure all modules in your spec can be imported:

```python
spec = {
    "my.custom.module.Class obj": {},
}

# Make sure my.custom.module is importable!
import my.custom.module
```

## Limitations

### 1. Dynamic Specs Not Supported

Compilation is static. If your spec changes at runtime, you can't use compilation:

```python
# This won't work with compilation
spec = {}
if os.getenv("PRODUCTION"):
    spec["db"] = {...}
else:
    spec["db"] = {...}  # Different spec!
```

### 2. Lambda Functions

Specs with lambdas can't be compiled:

```python
spec = {
    "MyClass obj": {"callback": lambda x: x * 2},  # Can't compile!
}
```

### 3. Complex Objects

Some Python objects can't be represented as code literals:

```python
import re

spec = {
    "regex": re.compile(r"\d+"),  # Can't compile!
}
```

For these cases, use constants in the compiled code or factory functions.

## Next Steps

- **[Basic Usage](basic-usage.md)** - Understand runtime wiring first
- **[Thread Safety](thread-safety.md)** - Learn about thread-safe compilation
- **[Async Support](async-support.md)** - Learn about async compilation
- **[Advanced Features](advanced.md)** - Advanced patterns and edge cases
