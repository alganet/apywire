# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

"""Core wiring functionality."""

import importlib
from typing import (
    Callable,
    Dict,
    List,
    Tuple,
    TypeAlias,
    cast,
)

InstanceData: TypeAlias = Dict[str, object]
Blueprint: TypeAlias = Tuple[str, str, str, InstanceData]

Spec: TypeAlias = Dict[str, InstanceData]


def _parse_spec(spec: Spec) -> List[Blueprint]:
    """Parses a Spec into Blueprints for instantiation."""
    items = []
    for key, value in spec.items():
        type_str, name = key.rsplit(" ", 1)
        parts = type_str.split(".")
        module_name = ".".join(parts[:-1])
        class_name = parts[-1]
        items.append((module_name, class_name, name, value))
    return items


class Wired:
    """Lazy-loaded container for wired objects."""

    def __init__(self, parsed: List[Blueprint]) -> None:
        self._parsed = {
            name: (module_name, class_name, value)
            for module_name, class_name, name, value in parsed
        }
        self._instances: Dict[str, object] = {}

    def __getattr__(self, name: str) -> object:
        """Get the instantiated object for name via attribute access."""
        if name not in self._parsed:
            raise AttributeError(f"no attribute '{name}'")
        if name not in self._instances:
            module_name, class_name, value = self._parsed[name]
            module = importlib.import_module(module_name)
            cls = cast(  # type: ignore[explicit-any,misc]
                # Less type-safe than generics but necessary for Cython
                Callable[..., object],
                getattr(module, class_name),
            )
            self._instances[name] = cls(**value)
        return self._instances[name]


def wire(spec: Spec) -> Wired:
    """Creates a lazy-loaded Wired object from a Spec."""
    return Wired(_parse_spec(spec))


def compile(spec: Spec) -> str:
    """Compiles a Spec into a string containing Python code."""
    parsed = _parse_spec(spec)
    modules = set()
    properties = []
    for module_name, class_name, name, value in parsed:
        modules.add(module_name)
        type_str = f"{module_name}.{class_name}"
        # value is always dict per type
        kwargs = ", ".join(f"{k}={repr(v)}" for k, v in value.items())
        prop = (
            "    @property\n"
            f"    def {name}(self):\n"
            f"        return {type_str}({kwargs})"
        )
        properties.append(prop)
    imports = [f"import {module}" for module in sorted(modules)]
    class_def = ["class Compiled:"] + properties + ["compiled = Compiled()"]
    return "\n".join(imports + class_def)
