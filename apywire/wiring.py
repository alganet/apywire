# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

"""Core wiring functionality."""

import ast
import importlib
from types import EllipsisType
from typing import (
    Callable,
    Dict,
    TypeAlias,
    cast,
)

ConstantValue: TypeAlias = (
    str | bytes | bool | int | float | complex | EllipsisType | None
)
InstanceData: TypeAlias = Dict[str, object | ConstantValue]
Spec: TypeAlias = Dict[str, InstanceData]


class Wiring:
    """Lazy-loaded container for wired objects."""

    def __init__(self, spec: Spec) -> None:
        parsed = []
        for key, value in spec.items():
            type_str, name = key.rsplit(" ", 1)
            parts = type_str.split(".")
            module_name = ".".join(parts[:-1])
            class_name = parts[-1]
            parsed.append((module_name, class_name, name, value))
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

    def compile(self) -> str:
        """Compiles the Spec into a string containing Python code."""
        # Build AST for the module
        body: list[ast.stmt] = []

        # Add import statements
        modules = set()
        for module_name, _, _ in self._parsed.values():
            modules.add(module_name)
        for module in sorted(modules):
            body.append(ast.Import(names=[ast.alias(name=module)]))

        # Build class body
        class_body: list[ast.stmt] = []
        for name, (module_name, class_name, value) in self._parsed.items():
            # Build the return statement: return module.class(**value)
            module_attr = ast.Attribute(
                value=ast.Name(id=module_name, ctx=ast.Load()),
                attr=class_name,
                ctx=ast.Load(),
            )
            kwargs = []
            for k, v in value.items():
                kwargs.append(
                    ast.keyword(k, value=ast.Constant(cast(ConstantValue, v)))
                )
            call = ast.Call(func=module_attr, args=[], keywords=kwargs)
            return_stmt = ast.Return(value=call)

            # Build function def for the property
            func_def = ast.FunctionDef(
                name=name,
                args=ast.arguments(
                    posonlyargs=[],
                    args=[ast.arg(arg="self")],
                    vararg=None,
                    kwarg=None,
                    defaults=[],
                    kwonlyargs=[],
                    kw_defaults=[],
                ),
                body=[return_stmt],
                decorator_list=[ast.Name(id="property", ctx=ast.Load())],
                returns=None,
                type_comment=None,
                type_params=[],
            )
            class_body.append(func_def)

        class_body = [ast.Pass()] if not class_body else class_body
        # Build class definition
        class_def = ast.ClassDef(
            name="Compiled",
            bases=[],
            keywords=[],
            body=class_body,
            decorator_list=[],
            type_params=[],
        )
        body.append(class_def)

        # Add compiled = Compiled()
        assign = ast.Assign(
            targets=[ast.Name(id="compiled", ctx=ast.Store())],
            value=ast.Call(
                func=ast.Name(id="Compiled", ctx=ast.Load()),
                args=[],
                keywords=[],
            ),
        )
        body.append(assign)

        # Create module AST
        module_ast = ast.Module(body=body, type_ignores=[])
        ast.fix_missing_locations(module_ast)

        # Unparse to string
        return ast.unparse(module_ast)
