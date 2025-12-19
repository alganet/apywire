<!--
SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>

SPDX-License-Identifier: ISC
-->

# Generator (Spec Generator)

The Generator utility can create apywire specs by introspecting class constructors.
It is useful for scaffolding a spec quickly for use with `Wiring` in tests or when
bootstrapping an application.

## Overview

`Generator` inspects the constructor signature (or a class factory method)
and generates a spec entry for the given type and instance name. For each
constructor parameter it creates:

- A placeholder for the parameter, e.g. `{instance_param}`
- A constant default value in the spec based on the parameter's type (when available)
- Or a recursive dependency entry if the parameter is another class type

The main entry point is `Generator.generate(*entries)`.

## Usage

Basic usage:

```python
from apywire import Generator, Wiring

spec = Generator.generate("datetime.datetime now")
wired = Wiring(spec)
now = wired.now()
```

You can generate multiple entries in a single call:

```python
spec = Generator.generate(
  "myapp.models.DateClass dt",
  "myapp.models.DeltaClass delta",
)

# Example output (spec dictionary):
expected_spec = {
  "myapp.models.DateClass dt": {
    "month": "{dt_month}",
    "year": "{dt_year}",
  },
  "myapp.models.DeltaClass delta": {
    "days": "{delta_days}",
  },
  "dt_month": 0,
  "dt_year": 0,
  "delta_days": 0,
}
```

Factory methods are supported by adding the factory method to the entry string:

```python
# Class with @classmethod create(cls, x) -> Instance
spec = Generator.generate("myapp.factories.WithFactory obj.create")

# Example output (spec dictionary):
expected_spec = {
  "myapp.factories.WithFactory obj.create": {
    "x": "{obj_x}",
  },
  "obj_x": 0,
}
```

## Behavior and Examples

- Parameter names are converted into placeholders using the instance name:
  a parameter `year` on instance `now` becomes placeholder `{now_year}`.
- Primitive and common types receive a sensible constant default:
  - `int`: 0, `float`: 0.0, `str`: "", `bool`: False, `bytes`: b"",
    `complex`: 0j, `None`: None
- `Optional[T]` (i.e., `Union[T, None]`) is resolved to the default for `T`.
- Complex unions default to `None`.
- `list`, `dict`, `tuple` defaults are `[]`, `{}`, and `()` respectively.
- Unknown or missing annotations default to `None`.
- Non-constant parameter defaults (e.g. object instances) fall back to type defaults.
- Dependencies (constructor parameters typed as another class) are generated
  recursively as separate spec entries, unless importing the dependency fails.
- Built-in types or types whose signatures cannot be inspected may result in an
  empty `{}` entry for that wiring key.

Example: Simple class

```python
class Simple:
    def __init__(self, year: int, month: int, day: int) -> None:
        ...

spec = Generator.generate("myapp.models.Simple now")

# Example output (spec dictionary):
expected_spec = {
    "myapp.models.Simple now": {
        "year": "{now_year}",
        "month": "{now_month}",
        "day": "{now_day}",
    },
    "now_year": 0,
    "now_month": 0,
    "now_day": 0,
}
```

Example: Dependency resolution

```python
class Inner:
    def __init__(self, value: int) -> None: ...

class Outer:
    def __init__(self, inner: Inner) -> None: ...

spec = Generator.generate("myapp.models.Outer wrapper")

# Example output (spec dictionary):
expected_spec = {
  "myapp.models.Inner wrapper_inner": {
    "value": "{wrapper_inner_value}",
  },
  "myapp.models.Outer wrapper": {
    "inner": "{wrapper_inner}",
  },
  "wrapper_inner_value": 0,
}
```

Example: Typed parameters

```python
class TypedClass:
    def __init__(
        self,
        int_param: int,
        str_param: str,
        float_param: float,
        bool_param: bool,
        opt_param: "Optional[str]" = None,
    ) -> None:
        pass

spec = Generator.generate("myapp.types.TypedClass obj")

# Example output (spec dictionary):
expected_spec = {
  "myapp.types.TypedClass obj": {
    "int_param": "{obj_int_param}",
    "str_param": "{obj_str_param}",
    "float_param": "{obj_float_param}",
    "bool_param": "{obj_bool_param}",
    "opt_param": "{obj_opt_param}",
  },
  "obj_int_param": 0,
  "obj_str_param": "",
  "obj_float_param": 0.0,
  "obj_bool_param": False,
  "obj_opt_param": None,
}
```

Example: Constant defaults preserved

```python
class WithDefaults:
    def __init__(self, name: str = "default_name", count: int = 100) -> None:
        pass

spec = Generator.generate("myapp.defaults.WithDefaults obj")

# Example output (spec dictionary):
expected_spec = {
  "myapp.defaults.WithDefaults obj": {
    "count": "{obj_count}",
    "name": "{obj_name}",
  },
  "obj_count": 100,
  "obj_name": "default_name",
}
```

Example: List and dict types

```python
class Container:
    def __init__(self, items: "List[int]", mapping: "Dict[str, int]") -> None:
        pass

spec = Generator.generate("myapp.containers.Container c")

# Example output (spec dictionary):
expected_spec = {
  "myapp.containers.Container c": {
    "items": "{c_items}",
    "mapping": "{c_mapping}",
  },
  "c_items": [],
  "c_mapping": {},
}
```

## API

### Generator.generate(*entries: str) -> apywire.Spec

Arguments:
- `entries`: Strings in the format `module.Class name` or
  `module.Class name.factoryMethod`.

Returns:
- A `Spec` dictionary ready for `Wiring`.

Raises:
- `ValueError` for invalid entry strings (e.g., missing delimiter or module)

## Notes and Limitations

- The generator bases decisions on constructor type annotations; without them
  the generator cannot reliably infer dependencies and will use `None`.
- For classes that use complex, programmatic defaults or runtime logic, the
  generator provides initial defaults but you should always review and adjust
  generated specs to fit runtime requirements.
- The generated spec is a suggestion and can be altered before passing to
  `Wiring`. It's useful for tests and bootstrapping but not intended to fully
  replace manual configuration in production.

## See Also

- `Wiring` (docs/user-guide/basic-usage.md)
- `apywire.Compiler` and the compiled wiring docs (user-guide/compilation.md)
