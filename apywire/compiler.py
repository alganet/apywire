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
    COMPILED_ARG_PREFIX,
    COMPILED_VAR_PREFIX,
    SYNTHETIC_CONST,
)
from apywire.wiring import (
    Spec,
    WiringBase,
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

    # Explicit attribute added for type checkers
    allow_partial: bool
    """Wiring container with compilation support."""

    def __init__(
        self,
        spec: Spec,
        *,
        thread_safe: bool = False,
        allow_partial: bool = False,
    ) -> None:
        """Initialize compiler with optional partial-construction support.

        Args:
            spec: wiring spec
            thread_safe: pack thread-safe behavior into generated code
            allow_partial: If True, the generated code will use a small helper
                module to support partial-construction placeholders for
                circular dependencies.
        """
        super().__init__(
            spec, thread_safe=thread_safe, allow_partial=allow_partial
        )
        self.allow_partial = allow_partial

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
        *,
        aio: bool,
        pre_statements: list[ast.stmt],
        counter: list[int],
    ) -> tuple[list[ast.expr], list[ast.keyword]]:
        """Process argument values and return AST expressions.

        For async mode, replaces awaits with local variables and generates
        pre-statements for variable assignments.

        Args:
            args_data: List of positional argument values
            kwargs_data: Dict of keyword argument values
            aio: Whether running in async mode
            pre_statements: List to accumulate assignment statements
            counter: Mutable counter for unique variable names

        Returns:
            Tuple of (args_list, kwargs_list) with AST expressions
        """
        args: list[ast.expr] = []
        kwargs: list[ast.keyword] = []

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

        return args, kwargs

    def _create_loop_assignment(self) -> ast.stmt:
        """Create AST statement for getting to running event loop."""
        return ast.Assign(
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

    def _create_executor_call(self, lambda_expr: ast.Lambda) -> ast.expr:
        """Create run_in_executor call for async compilation."""
        return ast.Await(
            value=ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id="loop", ctx=ast.Load()),
                    attr="run_in_executor",
                    ctx=ast.Load(),
                ),
                args=[ast.Constant(value=None), lambda_expr],
                keywords=[],
            )
        )

    def _create_function_template(
        self,
        name: str,
        body: list[ast.stmt],
        is_async: bool,
    ) -> ast.FunctionDef | ast.AsyncFunctionDef:
        """Create basic function definition structure."""
        if is_async:
            return ast.AsyncFunctionDef(
                name=name,
                args=_PROPERTY_ARGS,
                body=body,
                decorator_list=[],
                returns=None,
                type_comment=None,
                type_params=[],
            )
        else:
            return ast.FunctionDef(
                name=name,
                args=_PROPERTY_ARGS,
                body=body,
                decorator_list=[],
                returns=None,
                type_comment=None,
                type_params=[],
            )

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
        module_attr = self._create_module_reference(
            module_name, class_name, factory_method
        )
        pre_statements: list[ast.stmt] = []
        counter = [0]  # For generating unique variable names

        # Normalize and process argument data
        args_data, kwargs_data = self._normalize_spec_data(data)
        args, kwargs = self._process_argument_values(
            args_data,
            kwargs_data,
            aio=aio,
            pre_statements=pre_statements,
            counter=counter,
        )

        call = ast.Call(func=module_attr, args=args, keywords=kwargs)

        # If enabled, wrap the call in a helper that preserves partial
        # construction semantics for compiled code.
        if self.allow_partial:
            helper_call = ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id="apywire.partial", ctx=ast.Load()),
                    attr="_compiled_instantiate_with_partial",
                    ctx=ast.Load(),
                ),
                args=[
                    ast.Name(id="self", ctx=ast.Load()),
                    ast.Constant(value=name),
                    self._create_lambda_function(call),
                    ast.Attribute(
                        value=ast.Name(id=module_name, ctx=ast.Load()),
                        attr=class_name,
                        ctx=ast.Load(),
                    ),
                    ast.Constant(value=bool(factory_method)),
                ],
                keywords=[],
            )
            inst_expr = helper_call
        else:
            inst_expr = call

        cache_attr = f"{CACHE_ATTR_PREFIX}{name}"

        # Create reusable components
        has_check = self._create_cache_check(cache_attr)
        return_stmt = self._create_return_statement(cache_attr)
        # Build the assignment that sets the cache value; different
        # behavior is required for async vs sync callers.
        if not aio:
            assign_cache = self._create_cache_assignment(cache_attr, inst_expr)
        else:
            # Async path: compute local values and call in executor.
            lambda_expr = self._create_lambda_function(inst_expr)
            pre_statements.append(self._create_loop_assignment())
            run_call = self._create_executor_call(lambda_expr)
            assign_cache = self._create_cache_assignment(cache_attr, run_call)
        if_stmt_body = pre_statements.copy()
        if_stmt_body.append(assign_cache)
        if_stmt = ast.If(test=has_check, body=if_stmt_body, orelse=[])
        func_def: ast.FunctionDef | ast.AsyncFunctionDef
        # If the compiled output is thread-safe, inject locking logic
        if not aio and not thread_safe:
            func_def = self._create_function_template(
                name, [if_stmt, return_stmt], is_async=False
            )
        elif not aio and thread_safe:
            # Build sync thread-safe version using helper mixin
            maker = self._create_lambda_function(inst_expr)
            call_inst = ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id="self", ctx=ast.Load()),
                    attr="_instantiate_attr",
                    ctx=ast.Load(),
                ),
                args=[ast.Constant(value=name), maker],
                keywords=[],
            )
            assign_cache = self._create_cache_assignment(cache_attr, call_inst)
            if_stmt_body = pre_statements.copy()
            if_stmt_body.append(assign_cache)
            func_def = self._create_function_template(
                name,
                [
                    ast.If(test=has_check, body=if_stmt_body, orelse=[]),
                    return_stmt,
                ],
                is_async=False,
            )
        # This branch handles the asynchronous, non-thread-safe case
        elif aio and not thread_safe:
            func_def = self._create_function_template(
                name, [if_stmt, return_stmt], is_async=True
            )
        else:  # aio and thread_safe
            # Create a maker lambda (synchronous) for the helper
            # mixin and run it in executor. Precomputed locals are
            # already present in `pre_statements` to avoid 'await' in
            # the lambda body.
            maker = self._create_lambda_function(call)
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
            executor_lambda = self._create_lambda_function(instantiate_call)
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
            assign_cache = self._create_cache_assignment(cache_attr, run_call)
            body = pre_statements.copy()
            body.append(assign_cache)
            func_def = self._create_function_template(
                name,
                [ast.If(test=has_check, body=body, orelse=[]), return_stmt],
                is_async=True,
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
        # If compiler is configured to support partial construction, ensure
        # runtime helper is available in generated module.
        if self.allow_partial:
            modules.add("apywire.partial")
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
            elif module == "apywire.partial":
                # Import partial helper module used by compiled code
                imp = ast.Import(names=[ast.alias(name="apywire.partial")])
                body.append(imp)
            else:
                body.append(ast.Import(names=[ast.alias(name=module)]))

        # Build class body
        class_body: list[ast.stmt] = []
        # Add __init__ if needed to support thread-safety init and/or
        # partial-construction flag propagation.
        init_body: list[ast.stmt] = []
        needs_init = False
        if thread_safe:
            needs_init = True
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
        if self.allow_partial:
            needs_init = True
            # Set instance flag so compiled container behaves like runtime
            init_body.append(
                ast.Assign(
                    targets=[
                        ast.Attribute(
                            value=ast.Name(id="self", ctx=ast.Load()),
                            attr="allow_partial",
                            ctx=ast.Store(),
                        )
                    ],
                    value=ast.Constant(value=True),
                )
            )
        if needs_init:
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

            # Regular wired object
            class_body.append(
                self._compile_property(
                    name,
                    entry.module_name,
                    entry.class_name,
                    entry.factory_method,
                    cast(_ResolvedSpecMapping, entry.data),
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
        # ThreadSafeMixin and _LockUnavailableError imported from
        # apywire.threads rather than embedding helper code.
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
