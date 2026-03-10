# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC


"""Wiring compiler functionality."""

from __future__ import annotations

import ast
from operator import itemgetter
from types import EllipsisType
from typing import cast

from apywire.constants import (
    CACHE_ATTR_PREFIX,
    SYNTHETIC_CONST,
)
from apywire.wiring import (
    WiringBase,
    _AioWiredRef,
    _ConstantValue,
    _ResolvedSpecMapping,
    _ResolvedValue,
    _WiredRef,
)

_PROPERTY_ARGS = ast.arguments(
    posonlyargs=[],
    args=[ast.arg(arg="self")],
    vararg=None,
    kwarg=None,
    defaults=[],
    kwonlyargs=[],
    kw_defaults=[],
)


class WiringCompiler(WiringBase):
    """Wiring container with compilation support."""

    def _astify(self, obj: _ResolvedValue) -> ast.expr:
        """Convert a Python object (possibly a `_WiredRef`) to AST.

        Nested lists, tuples and dicts are supported. `_WiredRef` becomes
        an accessor call (`self.<name>()`) to mirror runtime behavior.

        `_AioWiredRef` becomes ``self.aio.<name>`` (an async accessor
        attribute access, no call).
        """
        if isinstance(obj, _AioWiredRef):
            # self.aio.name — attribute access, not a call
            return ast.Attribute(
                value=ast.Attribute(
                    value=ast.Name(id="self", ctx=ast.Load()),
                    attr="aio",
                    ctx=ast.Load(),
                ),
                attr=obj.name,
                ctx=ast.Load(),
            )
        if isinstance(obj, _WiredRef):
            # Access the wired value via `self.name()` in compiled code.
            return ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id="self", ctx=ast.Load()),
                    attr=obj.name,
                    ctx=ast.Load(),
                ),
                args=[],
                keywords=[],
            )
        if (
            isinstance(obj, (str, bytes, bool, int, float, complex))
            or obj is None
            or isinstance(obj, EllipsisType)
        ):
            return ast.Constant(obj)
        if isinstance(obj, dict):
            keys = [ast.Constant(k) for k in obj.keys()]
            values = [self._astify(v) for v in obj.values()]
            return ast.Dict(
                keys=cast(list[ast.expr | None], keys),
                values=values,
            )
        if isinstance(obj, list):
            elts = [self._astify(v) for v in obj]
            return ast.List(elts=elts, ctx=ast.Load())
        if isinstance(obj, tuple):
            elts = [self._astify(v) for v in obj]
            return ast.Tuple(elts=elts, ctx=ast.Load())
        return ast.Constant(cast(_ConstantValue, obj))

    def _normalize_spec_data(
        self, data: _ResolvedSpecMapping
    ) -> tuple[list[_ResolvedValue], dict[str, _ResolvedValue]]:
        """Normalize spec data into positional and keyword arguments.

        Args:
            data: Either a list (positional args only) or dict
                  (mixed args/kwargs)

        Returns:
            Tuple of (args_list, kwargs_dict)
        """
        args_data: list[_ResolvedValue] = []
        kwargs_data: dict[str, _ResolvedValue] = {}

        if isinstance(data, list):
            args_data = data
        else:
            data_dict = data
            # Separate args and kwargs from mixed dict
            args_items = []
            for k, v in data_dict.items():
                if isinstance(k, int):
                    args_items.append((k, v))
                elif isinstance(k, str):
                    kwargs_data[k] = v
            # Sort positional args by their integer keys
            args_items.sort(key=itemgetter(0))
            args_data = [v for _, v in args_items]

        return args_data, kwargs_data

    def _process_argument_values(
        self,
        args_data: list[_ResolvedValue],
        kwargs_data: dict[str, _ResolvedValue],
    ) -> tuple[list[ast.expr], list[ast.keyword]]:
        """Process argument values and return AST expressions.

        Args:
            args_data: List of positional argument values
            kwargs_data: Dict of keyword argument values

        Returns:
            Tuple of (args_list, kwargs_list) with AST expressions
        """
        args: list[ast.expr] = []
        kwargs: list[ast.keyword] = []

        for value in args_data:
            args.append(self._astify(value))

        for key, value in kwargs_data.items():
            kwargs.append(ast.keyword(arg=key, value=self._astify(value)))

        return args, kwargs

    def _create_module_reference(
        self, module_name: str, class_name: str, factory_method: str | None
    ) -> ast.expr:
        """Create AST reference to module.Class or module.Class.method."""
        if factory_method:
            return ast.Attribute(
                value=ast.Attribute(
                    value=ast.Name(id=module_name, ctx=ast.Load()),
                    attr=class_name,
                    ctx=ast.Load(),
                ),
                attr=factory_method,
                ctx=ast.Load(),
            )
        else:
            return ast.Attribute(
                value=ast.Name(id=module_name, ctx=ast.Load()),
                attr=class_name,
                ctx=ast.Load(),
            )

    def _create_cache_check(self, cache_attr: str) -> ast.expr:
        """Create hasattr check for cache attribute."""
        return ast.UnaryOp(
            op=ast.Not(),
            operand=ast.Call(
                func=ast.Name(id="hasattr", ctx=ast.Load()),
                args=[
                    ast.Name(id="self", ctx=ast.Load()),
                    ast.Constant(value=cache_attr),
                ],
                keywords=[],
            ),
        )

    def _create_return_statement(self, cache_attr: str) -> ast.stmt:
        """Create return statement for cached value."""
        return ast.Return(
            value=ast.Attribute(
                value=ast.Name(id="self", ctx=ast.Load()),
                attr=cache_attr,
                ctx=ast.Load(),
            )
        )

    def _create_cache_assignment(
        self, cache_attr: str, value_expr: ast.expr
    ) -> ast.stmt:
        """Create assignment to cache attribute."""
        return ast.Assign(
            targets=[
                ast.Attribute(
                    value=ast.Name(id="self", ctx=ast.Load()),
                    attr=cache_attr,
                    ctx=ast.Store(),
                )
            ],
            value=value_expr,
        )

    def _create_lambda_function(self, body: ast.expr) -> ast.Lambda:
        """Create a lambda function with the given body."""
        return ast.Lambda(
            args=ast.arguments(
                posonlyargs=[],
                args=[],
                vararg=None,
                kwarg=None,
                defaults=[],
                kwonlyargs=[],
                kw_defaults=[],
            ),
            body=body,
        )

    def _compile_property(
        self,
        name: str,
        module_name: str,
        class_name: str,
        factory_method: str | None,
        data: _ResolvedSpecMapping,
        *,
        thread_safe: bool = False,
    ) -> ast.FunctionDef:
        """Build an AST FunctionDef for a cached accessor that returns
        ``module.class(**data)`` or ``module.class.factory_method(**data)``.
        """
        # Build the target callable: module.Class or module.Class.factoryMethod
        module_attr = self._create_module_reference(
            module_name, class_name, factory_method
        )

        # Normalize and process argument data
        args_data, kwargs_data = self._normalize_spec_data(data)
        args, kwargs = self._process_argument_values(
            args_data,
            kwargs_data,
        )

        call = ast.Call(func=module_attr, args=args, keywords=kwargs)

        cache_attr = f"{CACHE_ATTR_PREFIX}{name}"

        # Create reusable components
        has_check = self._create_cache_check(cache_attr)
        return_stmt = self._create_return_statement(cache_attr)

        if not thread_safe:
            assign_cache = self._create_cache_assignment(cache_attr, call)
            if_stmt = ast.If(
                test=has_check, body=[assign_cache], orelse=[]
            )
            func_def = ast.FunctionDef(
                name=name,
                args=_PROPERTY_ARGS,
                body=[if_stmt, return_stmt],
                decorator_list=[],
                returns=None,
                type_comment=None,
                type_params=[],
            )
        else:
            # Build sync thread-safe version using helper mixin
            maker = self._create_lambda_function(call)
            call_inst = ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id="self", ctx=ast.Load()),
                    attr="_instantiate_attr",
                    ctx=ast.Load(),
                ),
                args=[ast.Constant(value=name), maker],
                keywords=[],
            )
            assign_cache = self._create_cache_assignment(
                cache_attr, call_inst
            )
            func_def = ast.FunctionDef(
                name=name,
                args=_PROPERTY_ARGS,
                body=[
                    ast.If(
                        test=has_check,
                        body=[assign_cache],
                        orelse=[],
                    ),
                    return_stmt,
                ],
                decorator_list=[],
                returns=None,
                type_comment=None,
                type_params=[],
            )
        return func_def

    def _compile_constant_property(
        self,
        name: str,
        value: _ConstantValue,
    ) -> ast.FunctionDef:
        """Return an AST FunctionDef for an accessor that returns a
        constant value.
        """
        return ast.FunctionDef(
            name=name,
            args=_PROPERTY_ARGS,
            body=[ast.Return(value=ast.Constant(value))],
            decorator_list=[],
            returns=None,
            type_comment=None,
            type_params=[],
        )

    def compile(self, *, aio: bool = False, thread_safe: bool = False) -> str:
        """Compiles the Spec into a string containing Python code.

        Args:
            aio: If True, keep sync ``def`` accessors AND add an
                ``.aio`` cached property (``CompiledAio`` wrapper).
                ``{aio.name}`` placeholders resolve to
                ``self.aio.name`` (async accessor attribute access).
            thread_safe: If True, generate thread-safe accessors using
                ``ThreadSafeMixin``.

        Returns:
            A string containing the Python source for the compiled
            `Compiled` container.
        """
        # Build AST for the module
        body: list[ast.stmt] = []

        # Add import statements
        modules = set()
        for module_name, _, _, _ in self._parsed.values():
            # Skip synthetic __pconst__ module
            if module_name != SYNTHETIC_CONST:
                modules.add(module_name)
        if thread_safe:
            # When compiling thread_safe, import thread-safety primitives
            modules.add("apywire.threads")
            modules.add("apywire.exceptions")
        for module in sorted(modules):
            if module == "apywire.threads":
                # Import ThreadSafeMixin from threads
                body.append(
                    ast.ImportFrom(
                        module="apywire.threads",
                        names=[
                            ast.alias(name="ThreadSafeMixin"),
                        ],
                        level=0,
                    )
                )
            elif module == "apywire.exceptions":
                # Import LockUnavailableError from exceptions
                body.append(
                    ast.ImportFrom(
                        module="apywire.exceptions",
                        names=[
                            ast.alias(name="LockUnavailableError"),
                        ],
                        level=0,
                    )
                )
            else:
                body.append(ast.Import(names=[ast.alias(name=module)]))
        if aio:
            # from functools import cached_property
            body.append(
                ast.ImportFrom(
                    module="functools",
                    names=[ast.alias(name="cached_property")],
                    level=0,
                )
            )
            # from apywire.runtime import CompiledAio
            body.append(
                ast.ImportFrom(
                    module="apywire.runtime",
                    names=[ast.alias(name="CompiledAio")],
                    level=0,
                )
            )

        # Build class body
        class_body: list[ast.stmt] = []

        # Collect constants for pre-caching (aio needs cache attrs)
        constant_names: dict[str, _ConstantValue] = {}
        if aio:
            for cname, cvalue in self._values.items():
                if cname not in self._parsed:
                    constant_names[cname] = cast(_ConstantValue, cvalue)

        # Generate __init__ if needed (thread_safe or aio constants)
        init_body: list[ast.stmt] = []
        if thread_safe:
            init_body.append(
                ast.Expr(
                    value=ast.Call(
                        func=ast.Attribute(
                            value=ast.Name(id="self", ctx=ast.Load()),
                            attr="_init_thread_safety",
                            ctx=ast.Load(),
                        ),
                        args=[],
                        keywords=[],
                    ),
                )
            )
        # Pre-populate cache attributes for constants so CompiledAio
        # can find them without going through run_in_executor.
        for cname, cvalue in constant_names.items():
            cache_attr = f"{CACHE_ATTR_PREFIX}{cname}"
            init_body.append(
                self._create_cache_assignment(
                    cache_attr, ast.Constant(cvalue)
                )
            )
        if init_body:
            init_def = ast.FunctionDef(
                name="__init__",
                args=_PROPERTY_ARGS,
                body=init_body,
                decorator_list=[],
                returns=None,
                type_params=[],
            )
            class_body.insert(0, init_def)

        for name, entry in self._parsed.items():
            # Skip synthetic auto-promoted constants
            # These require runtime interpolation and can't be pre-computed
            if (
                entry.module_name == SYNTHETIC_CONST
                and entry.class_name == "str"
            ):
                continue

            class_body.append(
                self._compile_property(
                    name,
                    entry.module_name,
                    entry.class_name,
                    entry.factory_method,
                    cast(_ResolvedSpecMapping, entry.data),
                    thread_safe=thread_safe,
                )
            )

        # Add constant accessors (names present in _values but not in parsed)
        for name, value in self._values.items():
            if name in self._parsed:
                continue
            class_body.append(
                self._compile_constant_property(
                    name,
                    cast(_ConstantValue, value),
                )
            )

        # When aio=True, append .aio cached property
        if aio:
            # @cached_property
            # def aio(self):
            #     return CompiledAio(self)
            aio_prop = ast.FunctionDef(
                name="aio",
                args=_PROPERTY_ARGS,
                body=[
                    ast.Return(
                        value=ast.Call(
                            func=ast.Name(id="CompiledAio", ctx=ast.Load()),
                            args=[
                                ast.Name(id="self", ctx=ast.Load()),
                            ],
                            keywords=[],
                        )
                    )
                ],
                decorator_list=[
                    ast.Name(id="cached_property", ctx=ast.Load()),
                ],
                returns=None,
                type_comment=None,
                type_params=[],
            )
            class_body.append(aio_prop)

        class_body = [ast.Pass()] if not class_body else class_body
        # Build class definition
        class_bases: list[ast.expr] = []
        if thread_safe:
            class_bases.append(ast.Name(id="ThreadSafeMixin", ctx=ast.Load()))
        class_def = ast.ClassDef(
            name="Compiled",
            bases=class_bases,
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
