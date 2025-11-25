# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC


"""Wiring compiler functionality."""

from __future__ import annotations

import ast
from types import EllipsisType
from typing import cast

from apywire.constants import (
    CACHE_ATTR_PREFIX,
    COMPILED_ARG_PREFIX,
    COMPILED_VAR_PREFIX,
    SYNTHETIC_CONST,
)
from apywire.wiring import (
    WiringBase,
    _ConstantValue,
    _ResolvedSpecMapping,
    _ResolvedValue,
    _WiredRef,
)

# Constant for property AST arguments (used in compile methods)
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

    def _astify(self, obj: _ResolvedValue, aio: bool = False) -> ast.expr:
        """Convert a Python object (possibly a `_WiredRef`) to AST.

        Nested lists, tuples and dicts are supported. `_WiredRef` becomes
        an accessor call (`self.<name>()`) to mirror runtime behavior.

        If ``aio`` is True, `_WiredRef` becomes an awaited accessor
        (`await self.<name>()`) to reflect the asynchronous compiled
        code's behavior.
        """
        if isinstance(obj, _WiredRef):
            # Access the wired value via `self.name()` in compiled code.
            call = ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id="self", ctx=ast.Load()),
                    attr=obj.name,
                    ctx=ast.Load(),
                ),
                args=[],
                keywords=[],
            )
            if aio:
                return ast.Await(value=call)
            return call
        if (
            isinstance(obj, (str, bytes, bool, int, float, complex))
            or obj is None
            or isinstance(obj, EllipsisType)
        ):
            return ast.Constant(obj)
        if isinstance(obj, dict):
            keys = [ast.Constant(k) for k in obj.keys()]
            values = [self._astify(v, aio=aio) for v in obj.values()]
            return ast.Dict(
                keys=cast(list[ast.expr | None], keys),
                values=values,
            )
        if isinstance(obj, list):
            elts = [self._astify(v, aio=aio) for v in obj]
            return ast.List(elts=elts, ctx=ast.Load())
        if isinstance(obj, tuple):
            elts = [self._astify(v, aio=aio) for v in obj]
            return ast.Tuple(elts=elts, ctx=ast.Load())
        return ast.Constant(cast(_ConstantValue, obj))

    def _compile_property(
        self,
        name: str,
        module_name: str,
        class_name: str,
        factory_method: str | None,
        data: _ResolvedSpecMapping,
        *,
        aio: bool = False,
        thread_safe: bool = False,
    ) -> ast.FunctionDef | ast.AsyncFunctionDef:
        """Build an AST FunctionDef for a cached accessor that returns
        ``module.class(**data)`` or ``module.class.factory_method(**data)``.

        When ``aio`` is True this function will produce an
        ``ast.AsyncFunctionDef`` that awaits referenced accessors and calls
        the blocking constructor in an executor (``loop.run_in_executor``).
        When ``aio`` is False it produces a standard synchronous
        ``ast.FunctionDef``.
        """
        # Build the target callable: module.Class or module.Class.factoryMethod
        if factory_method:
            module_attr = ast.Attribute(
                value=ast.Attribute(
                    value=ast.Name(id=module_name, ctx=ast.Load()),
                    attr=class_name,
                    ctx=ast.Load(),
                ),
                attr=factory_method,
                ctx=ast.Load(),
            )
        else:
            module_attr = ast.Attribute(
                value=ast.Name(id=module_name, ctx=ast.Load()),
                attr=class_name,
                ctx=ast.Load(),
            )
        kwargs: list[ast.keyword] = []
        # When compiling async accessors we must precompute awaited
        # referenced attributes into locals so that the constructor
        # lambda passed to a thread pool executor is pure synchronous.
        pre_statements: list[ast.stmt] = []

        # Counter for generating unique variable names (mutable list)
        counter = [0]

        args: list[ast.expr] = []

        # Normalize data into args_data (list) and kwargs_data (dict)
        args_data: list[_ResolvedValue] = []
        kwargs_data: dict[str, _ResolvedValue] = {}

        if isinstance(data, list):
            args_data = data
        else:
            data_dict = data
            int_keys = sorted(k for k in data_dict if isinstance(k, int))
            str_keys = [k for k in data_dict if isinstance(k, str)]
            for k_int in int_keys:
                args_data.append(data_dict[k_int])
            for k_str in str_keys:
                kwargs_data[k_str] = data_dict[k_str]

        # Process positional args
        for i, value in enumerate(args_data):
            raw_val_ast = self._astify(value, aio=aio)
            if aio:
                val_ast = self._replace_awaits_with_locals(
                    raw_val_ast, pre_statements, counter
                )
                var_name = f"{COMPILED_ARG_PREFIX}{i}"
                assign = ast.Assign(
                    targets=[ast.Name(id=var_name, ctx=ast.Store())],
                    value=val_ast,
                )
                pre_statements.append(assign)
                arg_val: ast.expr = ast.Name(id=var_name, ctx=ast.Load())
            else:
                arg_val = raw_val_ast
            args.append(arg_val)

        # Process keyword args
        for key, value in kwargs_data.items():
            raw_val_ast = self._astify(value, aio=aio)
            if aio:
                # Replace any awaited accessors with local precomputed
                # variables and assign all values to local variables so
                # that the executor lambda can be synchronous.
                val_ast = self._replace_awaits_with_locals(
                    raw_val_ast, pre_statements, counter
                )
                # Use named variables for top-level keyword args to make
                # the generated code more readable and deterministic.
                var_name = f"{COMPILED_VAR_PREFIX}{key}"
                assign = ast.Assign(
                    targets=[ast.Name(id=var_name, ctx=ast.Store())],
                    value=val_ast,
                )
                pre_statements.append(assign)
                kw_val: ast.expr = ast.Name(id=var_name, ctx=ast.Load())
            else:
                kw_val = raw_val_ast
            kwargs.append(ast.keyword(arg=key, value=kw_val))

        # Build the actual constructor call (module.Class(*args, **kwargs))
        call = ast.Call(func=module_attr, args=args, keywords=kwargs)

        # Cache attribute name like `_name` used to store instantiated
        # objects on `self` at runtime. The compiled accessor returns
        # `self._name` when present.
        cache_attr = f"{CACHE_ATTR_PREFIX}{name}"

        # if not hasattr(self, '_name'): ...
        has_check = ast.UnaryOp(
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

        return_stmt = ast.Return(
            value=ast.Attribute(
                value=ast.Name(id="self", ctx=ast.Load()),
                attr=cache_attr,
                ctx=ast.Load(),
            )
        )
        # Build the assignment that sets the cache value; different
        # behavior is required for async vs sync callers.
        if not aio:
            assign_cache = ast.Assign(
                targets=[
                    ast.Attribute(
                        value=ast.Name(id="self", ctx=ast.Load()),
                        attr=cache_attr,
                        ctx=ast.Store(),
                    )
                ],
                value=call,
            )
        else:
            # Async path: compute local values and call in executor.
            loop_assign = ast.Assign(
                targets=[ast.Name(id="loop", ctx=ast.Store())],
                value=ast.Call(
                    func=ast.Attribute(
                        value=ast.Name(id="asyncio", ctx=ast.Load()),
                        attr="get_running_loop",
                        ctx=ast.Load(),
                    ),
                    args=[],
                    keywords=[],
                ),
            )
            # Create a lambda that returns the class call expression
            # referencing the precomputed locals
            lambda_expr = ast.Lambda(
                args=ast.arguments(
                    posonlyargs=[],
                    args=[],
                    vararg=None,
                    kwarg=None,
                    defaults=[],
                    kwonlyargs=[],
                    kw_defaults=[],
                ),
                body=call,
            )
            run_call = ast.Await(
                value=ast.Call(
                    func=ast.Attribute(
                        value=ast.Name(id="loop", ctx=ast.Load()),
                        attr="run_in_executor",
                        ctx=ast.Load(),
                    ),
                    args=[
                        ast.Constant(value=None),
                        lambda_expr,
                    ],
                    keywords=[],
                )
            )
            assign_cache = ast.Assign(
                targets=[
                    ast.Attribute(
                        value=ast.Name(id="self", ctx=ast.Load()),
                        attr=cache_attr,
                        ctx=ast.Store(),
                    )
                ],
                value=run_call,
            )
        if_stmt_body = pre_statements.copy()
        if aio:
            if_stmt_body.append(loop_assign)
        if_stmt_body.append(assign_cache)
        if_stmt = ast.If(test=has_check, body=if_stmt_body, orelse=[])
        func_def: ast.FunctionDef | ast.AsyncFunctionDef
        # If the compiled output is thread-safe, inject locking logic
        if not aio and not thread_safe:
            func_def = ast.FunctionDef(
                name=name,
                args=_PROPERTY_ARGS,
                body=[if_stmt, return_stmt],
                decorator_list=[],
                returns=None,
                type_comment=None,
                type_params=[],
            )
        elif not aio and thread_safe:
            # Build sync thread-safe version using code template
            # Build a lambda maker which is a synchronous callable used by
            # the helper mixin to invoke the constructor within the
            # instantiation lock management. We pass this maker to
            # `self._instantiate_attr(name, maker)`.
            maker = ast.Lambda(
                args=ast.arguments(
                    posonlyargs=[],
                    args=[],
                    vararg=None,
                    kwarg=None,
                    defaults=[],
                    kwonlyargs=[],
                    kw_defaults=[],
                ),
                body=call,
            )
            call_inst = ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id="self", ctx=ast.Load()),
                    attr="_instantiate_attr",
                    ctx=ast.Load(),
                ),
                args=[ast.Constant(value=name), maker],
                keywords=[],
            )
            assign_cache = ast.Assign(
                targets=[
                    ast.Attribute(
                        value=ast.Name(id="self", ctx=ast.Load()),
                        attr=cache_attr,
                        ctx=ast.Store(),
                    )
                ],
                value=call_inst,
            )
            if_stmt_body = pre_statements.copy()
            if_stmt_body.append(assign_cache)
            func_def = ast.FunctionDef(
                name=name,
                args=_PROPERTY_ARGS,
                body=[
                    ast.If(test=has_check, body=if_stmt_body, orelse=[]),
                    return_stmt,
                ],
                decorator_list=[],
                returns=None,
                type_comment=None,
                type_params=[],
            )
        # This branch handles the synchronous, non-thread-safe case
        elif aio and not thread_safe:
            func_def = ast.AsyncFunctionDef(
                name=name,
                args=_PROPERTY_ARGS,
                body=[if_stmt, return_stmt],
                decorator_list=[],
                returns=None,
                type_comment=None,
                type_params=[],
            )
        else:  # aio and thread_safe
            # Create a maker lambda (synchronous) for the helper
            # mixin and run it in executor. Precomputed locals are
            # already present in `pre_statements` to avoid 'await' in
            # the lambda body.
            maker = ast.Lambda(
                args=ast.arguments(
                    posonlyargs=[],
                    args=[],
                    vararg=None,
                    kwarg=None,
                    defaults=[],
                    kwonlyargs=[],
                    kw_defaults=[],
                ),
                body=call,
            )
            instantiate_call = ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id="self", ctx=ast.Load()),
                    attr="_instantiate_attr",
                    ctx=ast.Load(),
                ),
                args=[ast.Constant(value=name), maker],
                keywords=[],
            )
            # Build lambda passed to executor that calls the mixin
            executor_lambda = ast.Lambda(
                args=ast.arguments(
                    posonlyargs=[],
                    args=[],
                    vararg=None,
                    kwarg=None,
                    defaults=[],
                    kwonlyargs=[],
                    kw_defaults=[],
                ),
                body=instantiate_call,
            )
            run_call = ast.Await(
                value=ast.Call(
                    func=ast.Attribute(
                        value=ast.Name(id="loop", ctx=ast.Load()),
                        attr="run_in_executor",
                        ctx=ast.Load(),
                    ),
                    args=[ast.Constant(value=None), executor_lambda],
                    keywords=[],
                )
            )
            assign_cache = ast.Assign(
                targets=[
                    ast.Attribute(
                        value=ast.Name(id="self", ctx=ast.Load()),
                        attr=cache_attr,
                        ctx=ast.Store(),
                    )
                ],
                value=run_call,
            )
            body = pre_statements.copy()
            # Ensure we compute the event loop variable before calling into
            # run_in_executor.
            body.append(loop_assign)
            body.append(assign_cache)
            func_def = ast.AsyncFunctionDef(
                name=name,
                args=_PROPERTY_ARGS,
                body=[
                    ast.If(test=has_check, body=body, orelse=[]),
                    return_stmt,
                ],
                decorator_list=[],
                returns=None,
                type_comment=None,
                type_params=[],
            )
        return func_def

    def _replace_awaits_with_locals(
        self,
        node: ast.expr,
        pre_statements: list[ast.stmt],
        counter: list[int],
    ) -> ast.expr:
        """Replace await expressions with local variable assignments.

        Recursively processes AST nodes to replace `ast.Await` expressions
        with local variable assignments. This ensures that synchronous lambdas
        executed in a thread pool do not contain `await` nodes.

        Args:
            node: AST expression node to process
            pre_statements: List to accumulate pre-computation statements
            counter: Single-element list used as mutable counter for var naming

        Returns:
            Transformed AST expression node
        """
        if isinstance(node, ast.Await):
            inner = node.value
            if (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Attribute)
                and isinstance(inner.func.value, ast.Name)
                and inner.func.value.id == "self"
            ):
                # produce a unique variable name and precompute the await
                counter[0] += 1
                var_name = f"{COMPILED_VAR_PREFIX}{counter[0]}"
                assign = ast.Assign(
                    targets=[ast.Name(id=var_name, ctx=ast.Store())],
                    value=node,
                )
                pre_statements.append(assign)
                return ast.Name(id=var_name, ctx=ast.Load())
            return node

        # Recurse into common composite nodes
        if isinstance(node, ast.Call):
            new_args = [
                self._replace_awaits_with_locals(a, pre_statements, counter)
                for a in node.args
            ]
            new_keywords = [
                ast.keyword(
                    arg=k.arg,
                    value=self._replace_awaits_with_locals(
                        k.value, pre_statements, counter
                    ),
                )
                for k in node.keywords
            ]
            return ast.Call(
                func=node.func, args=new_args, keywords=new_keywords
            )
        if isinstance(node, ast.Dict):
            new_keys = [
                (
                    self._replace_awaits_with_locals(
                        k, pre_statements, counter
                    )
                    if k is not None
                    else None
                )
                for k in node.keys
            ]
            new_values = [
                self._replace_awaits_with_locals(v, pre_statements, counter)
                for v in node.values
            ]
            return ast.Dict(keys=new_keys, values=new_values)
        if isinstance(node, ast.List):
            return ast.List(
                elts=[
                    self._replace_awaits_with_locals(
                        e, pre_statements, counter
                    )
                    for e in node.elts
                ],
                ctx=node.ctx,
            )
        if isinstance(node, ast.Tuple):
            return ast.Tuple(
                elts=[
                    self._replace_awaits_with_locals(
                        e, pre_statements, counter
                    )
                    for e in node.elts
                ],
                ctx=node.ctx,
            )
        return node

    def _compile_constant_property(
        self,
        name: str,
        value: _ConstantValue,
        *,
        aio: bool = False,
    ) -> ast.FunctionDef | ast.AsyncFunctionDef:
        """Return an AST FunctionDef for an accessor that returns a
        constant value.

        When ``aio`` is True the compiled accessor will be an
        ``async def`` that returns the constant directly (no executor
        required), otherwise a synchronous ``def`` is emitted.
        """
        return_stmt = ast.Return(value=ast.Constant(value))
        func_def: ast.FunctionDef | ast.AsyncFunctionDef
        if not aio:
            func_def = ast.FunctionDef(
                name=name,
                args=_PROPERTY_ARGS,
                body=[return_stmt],
                decorator_list=[],
                returns=None,
                type_comment=None,
                type_params=[],
            )
        else:
            func_def = ast.AsyncFunctionDef(
                name=name,
                args=_PROPERTY_ARGS,
                body=[return_stmt],
                decorator_list=[],
                returns=None,
                type_comment=None,
                type_params=[],
            )
        return func_def

    def compile(self, *, aio: bool = False, thread_safe: bool = False) -> str:
        """Compiles the Spec into a string containing Python code.

        Args:
            aio: If True, generate `async def` accessors for wired
                attributes that await referenced attributes and call
                blocking constructors in a threadpool via
                `asyncio.get_running_loop().run_in_executor`. When False
                (default) generate synchronous `def` accessors.

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
        if aio:
            modules.add("asyncio")
        if thread_safe:
            # When compiling thread_safe, import thread-safety primitives
            modules.add("apywire.threads")
            modules.add("apywire.exceptions")
        for module in sorted(modules):
            if module == "apywire.threads":
                # Import CompiledThreadSafeMixin from threads
                body.append(
                    ast.ImportFrom(
                        module="apywire.threads",
                        names=[
                            ast.alias(name="CompiledThreadSafeMixin"),
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

        # Build class body
        class_body: list[ast.stmt] = []
        # When thread safe, add __init__ that calls helper mixin init
        if thread_safe:
            # class __init__
            init_body: list[ast.stmt] = []
            # compiled class will inherit from the mixin and just call
            # `_init_thread_safety` from its constructor
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
            init_def = ast.FunctionDef(
                name="__init__",
                args=_PROPERTY_ARGS,
                body=init_body,
                decorator_list=[],
                returns=None,
                type_params=[],
            )
            class_body.insert(0, init_def)
        for name, (
            module_name,
            class_name,
            factory_method,
            data,
        ) in self._parsed.items():
            # Skip synthetic auto-promoted constants
            # These require runtime interpolation and can't be pre-computed
            if module_name == SYNTHETIC_CONST and class_name == "str":
                continue

            # Regular wired object
            class_body.append(
                self._compile_property(
                    name,
                    module_name,
                    class_name,
                    factory_method,
                    cast(_ResolvedSpecMapping, data),
                    aio=aio,
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
                    aio=aio,
                )
            )

        class_body = [ast.Pass()] if not class_body else class_body
        # When using thread_safe compiled output we will rely on the
        # CompiledThreadSafeMixin and _LockUnavailableError imported from
        # apywire.threads rather than embedding helper code.
        # Build class definition
        class_bases: list[ast.expr] = []
        if thread_safe:
            class_bases.append(
                ast.Name(id="CompiledThreadSafeMixin", ctx=ast.Load())
            )
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
