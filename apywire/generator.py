# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

"""Spec generator from class introspection.

This module provides the Generator class for creating apywire specs
by inspecting class constructors and their type annotations.
"""

from __future__ import annotations

import importlib
import inspect
from types import ModuleType, NoneType
from typing import (
    Union,
    cast,
    get_args,
    get_origin,
)

from apywire.constants import (
    PLACEHOLDER_END,
    PLACEHOLDER_START,
)
from apywire.runtime import _Constructor
from apywire.wiring import Spec, SpecParser, _ConstantValue, _SpecMapping

# Parameter sentinel values
_PARAM_EMPTY: object = inspect.Parameter.empty  # type: ignore[misc]
_VAR_POSITIONAL: object = (
    inspect.Parameter.VAR_POSITIONAL  # type: ignore[misc]
)
_VAR_KEYWORD: object = inspect.Parameter.VAR_KEYWORD  # type: ignore[misc]


class Generator(SpecParser):
    """Generates apywire specs from class introspection.

    This class inspects class constructors to automatically generate
    spec dictionaries with type-appropriate default values and
    placeholder references.

    Example:
        >>> spec = Generator.generate("datetime.datetime now")
        >>> # Returns spec with now_year, now_month, now_day, etc.
    """

    # Default values for common types
    _TYPE_DEFAULTS: dict[type, _ConstantValue] = {
        int: 0,
        float: 0.0,
        str: "",
        bool: False,
        bytes: b"",
        complex: 0j,
        NoneType: None,
    }

    @classmethod
    def generate(cls, *entries: str) -> Spec:
        """Generate a spec from one or more class entry strings.

        Args:
            *entries: Entry strings in format "module.Class name" or
                      "module.Class name.factoryMethod"

        Returns:
            A spec dictionary suitable for use with apywire.Wiring

        Raises:
            ValueError: If entry format is invalid

        Example:
            >>> spec = Generator.generate("datetime.datetime now")
            >>> wired = Wiring(spec)
        """
        spec: Spec = {}
        visited: set[str] = set()

        for entry in entries:
            cls._process_entry(entry, spec, visited)

        return spec

    @classmethod
    def _process_entry(cls, entry: str, spec: Spec, visited: set[str]) -> None:
        """Process a single entry and add it to the spec.

        Args:
            entry: Entry string like "module.Class name"
            spec: Spec dict to populate
            visited: Set of already-visited class keys to detect cycles
        """
        parsed = cls._parse_request_string(entry)
        if parsed is None:
            raise ValueError(
                f"Invalid entry format '{entry}': "
                f"expected 'module.Class name'"
            )
        module_name, class_name, instance_name, factory_method = parsed

        # Build the spec key
        type_path = f"{module_name}.{class_name}"
        spec_key = f"{type_path} {instance_name}"
        if factory_method:
            spec_key = f"{type_path} {instance_name}.{factory_method}"

        # Check for circular dependency
        if spec_key in visited:
            # Cycle detected: stop recursion. The runtime container will
            # handle the cycle (or raise error) when resolving.
            return
        visited.add(spec_key)

        # Import the class
        module: ModuleType = importlib.import_module(module_name)
        target_class: type = cast(type, getattr(module, class_name))

        # Determine what to inspect
        sig: inspect.Signature
        try:
            if factory_method:
                callable_obj: _Constructor = cast(
                    _Constructor, getattr(target_class, factory_method)
                )
                sig = inspect.signature(callable_obj)
            else:
                # For classes, use __init__
                init_method: _Constructor | None = cast(
                    _Constructor | None,
                    getattr(target_class, "__init__", None),
                )
                if init_method is not None:
                    sig = inspect.signature(init_method)
                else:
                    spec[spec_key] = {}
                    return
        except (ValueError, TypeError, RecursionError):
            # Some built-in classes (or pathological annotations) don't have
            # inspectable signatures; fall back to an empty entry to avoid
            # infinite recursion.
            spec[spec_key] = {}
            return

        # Build params dict for this class
        params: dict[str, str] = {}

        for param_name, param in sig.parameters.items():
            # Skip self, cls, *args, **kwargs
            if param_name in ("self", "cls"):
                continue
            param_kind: object = param.kind
            if param_kind in (_VAR_POSITIONAL, _VAR_KEYWORD):
                continue

            # Get type annotation
            annotation: object | None = cast(object | None, param.annotation)
            if annotation is _PARAM_EMPTY:
                annotation = None

            # Check if it has a default value
            param_default: object = cast(object, param.default)
            has_default = param_default is not _PARAM_EMPTY

            # Generate constant name for this parameter
            const_name = f"{instance_name}_{param_name}"

            # Determine default value based on type
            default_value, is_dependency = cls._get_default_for_type(
                annotation, const_name, spec, visited, module_name
            )

            placeholder = f"{PLACEHOLDER_START}{const_name}{PLACEHOLDER_END}"
            params[param_name] = placeholder

            if not is_dependency:
                # For non-dependency params, set a constant value
                if has_default and cls._is_spec_constant(param_default):
                    spec[const_name] = cast(_ConstantValue, param_default)
                else:
                    spec[const_name] = default_value

        spec[spec_key] = cast(_SpecMapping, params)

    @classmethod
    def _get_default_for_type(
        cls,
        annotation: object,
        const_name: str,
        spec: Spec,
        visited: set[str],
        current_module: str,
    ) -> tuple[_ConstantValue, bool]:
        """Get a default value for a type annotation.

        Args:
            annotation: The type annotation (may be None)
            const_name: Name for the constant (used as instance name for deps)
            spec: Spec dict to populate with dependencies
            visited: Set of visited class keys for cycle detection
            current_module: Module name for resolving relative types

        Returns:
            Tuple of (default_value, is_dependency)
            - default_value: The constant default value
            - is_dependency: True if this created a dependency entry
        """
        if annotation is None:
            return None, False

        # Handle typing module constructs
        origin: object | None = cast(object | None, get_origin(annotation))
        args: tuple[object, ...] = cast(
            tuple[object, ...], get_args(annotation)
        )

        # Optional[X] is Union[X, None]
        if origin is Union:
            # Filter out NoneType
            non_none_args: list[object] = [
                a for a in args if a is not type(None)
            ]
            if len(non_none_args) == 1:
                # It's Optional[X], recurse with X
                return cls._get_default_for_type(
                    non_none_args[0], const_name, spec, visited, current_module
                )
            # Complex union, default to None
            return None, False

        # list, List[T]
        if origin is list:
            return cast(_ConstantValue, []), False

        # dict, Dict[K, V]
        if origin is dict:
            return cast(_ConstantValue, {}), False

        # tuple, Tuple[...]
        if origin is tuple:
            return cast(_ConstantValue, ()), False

        # Check if it's a basic type we know
        if isinstance(annotation, type):  # type: ignore[misc]
            if annotation in cls._TYPE_DEFAULTS:
                return cls._TYPE_DEFAULTS[annotation], False

            # It's a class type - generate as dependency
            return cls._generate_dependency(
                annotation,
                const_name,
                spec,
                visited,
                current_module,
            )

        # Unknown annotation type
        return None, False

    @classmethod
    def _generate_dependency(
        cls,
        dep_class: type,
        instance_name: str,
        spec: Spec,
        visited: set[str],
        current_module: str,
    ) -> tuple[_ConstantValue, bool]:
        """Generate a spec entry for a dependency class.

        Args:
            dep_class: The class to generate
            instance_name: Instance name for this dependency
            spec: Spec dict to populate
            visited: Set of visited class keys
            current_module: Fallback module name

        Returns:
            Tuple of (None, True) indicating this is a dependency
        """
        class_name = dep_class.__name__
        module_attr: object | None = getattr(
            dep_class, "__module__", current_module
        )
        if isinstance(module_attr, str) and module_attr:
            module_name = module_attr
        else:
            module_name = current_module

        # Build entry string
        entry = f"{module_name}.{class_name} {instance_name}"

        # Recursively process (will add to spec)
        try:
            # Propagate the same visited set so that cycles are detected
            cls._process_entry(entry, spec, visited)
        except (AttributeError, ModuleNotFoundError):
            # If can't find module, just reference it
            pass

        return None, True
