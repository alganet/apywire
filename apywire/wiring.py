# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC


"""Core wiring functionality."""

from __future__ import annotations

import ast
import asyncio
import importlib
from types import EllipsisType
from typing import Awaitable, Callable, TypeAlias, cast, final

from apywire.exceptions import (
    CircularWiringError,
    UnknownPlaceholderError,
    WiringError,
)
from apywire.thread_safety import CompiledThreadSafeMixin, ThreadLocalState

_ConstantValue: TypeAlias = (
    str | bytes | bool | int | float | complex | EllipsisType | None
)


# Marker class for a placeholder reference. Declared before the
# type aliases so `ResolvedValue` can reference it directly.
class _WiredRef:
    """Marker for a value that references another wired attribute.

    Resolved lazily at instantiation.
    """

    __slots__ = ("name",)

    def __init__(self, name: str) -> None:
        self.name = name


# Spec value types come from the user-provided `Spec` input. They are
# primitives or nested containers and may include placeholder strings
# like "{otherName}".
_SpecValue: TypeAlias = (
    _ConstantValue
    | str
    | list["_SpecValue"]
    | tuple["_SpecValue", ...]
    | dict[str, "_SpecValue"]
)

# Resolved values are produced after parsing placeholders; strings of
# the form "{name}" become `_WiredRef` markers and are resolved at
# instantiation.
_ResolvedValue: TypeAlias = (
    _ConstantValue
    | _WiredRef
    | list["_ResolvedValue"]
    | tuple["_ResolvedValue", ...]
    | dict[str, "_ResolvedValue"]
)

# Runtime values are the concrete types available at runtime —
# constants, objects and nested containers.
_RuntimeValue: TypeAlias = (
    object
    | _ConstantValue
    | list["_RuntimeValue"]
    | tuple["_RuntimeValue", ...]
    | dict[str, "_RuntimeValue"]
)

_SpecMapping: TypeAlias = dict[str, _SpecValue]
# Public alias to annotate an individual spec mapping entry.
# Example: `def build(spec: apywire.SpecEntry) -> apywire.Spec: ...`
SpecEntry: TypeAlias = dict[str, _SpecValue]
_ResolvedSpecMapping: TypeAlias = dict[str, _ResolvedValue]
Spec: TypeAlias = dict[str, _SpecMapping | _ConstantValue]

# Type aliases for parsed spec entries
_ParsedEntry: TypeAlias = tuple[
    str, str, _ResolvedSpecMapping
]  # (module, class, data)
_UnresolvedParsedEntry: TypeAlias = tuple[
    str, str, str, _SpecMapping
]  # (module, class, name, data)


class _ThreadLocalState(ThreadLocalState):
    """Thread-local state for wiring resolution.

    Inherits from ThreadLocalState to get properly typed attributes.
    """


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


class Wiring(CompiledThreadSafeMixin):
    """Lazy-loaded container for wired objects."""

    _parsed: dict[str, _ParsedEntry]
    _values: dict[str, _RuntimeValue]

    def __init__(
        self,
        spec: Spec,
        *,
        thread_safe: bool = False,
        max_lock_attempts: int = 10,
        lock_retry_sleep: float = 0.01,
    ) -> None:
        """Initialize a Wiring container.

        Args:
            spec: The wiring spec mapping.
            thread_safe: Enable thread-safe instantiation (default: False).
            max_lock_attempts: Max retries in global lock mode
                               (only when thread_safe=True).
            lock_retry_sleep: Sleep time in seconds between lock retries
                              (only when thread_safe=True).
        """
        self._thread_safe = thread_safe
        self._max_lock_attempts = max_lock_attempts
        self._lock_retry_sleep = lock_retry_sleep

        parsed: list[_UnresolvedParsedEntry] = []
        consts: dict[str, _ConstantValue] = {}

        # First pass: classify entries into wired classes or constants
        for key, value in spec.items():
            entry = self._parse_spec_entry(key, value)
            if entry is not None:
                parsed.append(entry)
            else:
                # It's a constant
                consts[key] = cast(_ConstantValue, value)

        # Merge constants into the initial runtime cache
        self._values: dict[str, _RuntimeValue] = dict(consts)

        # Resolve placeholders like "{name}" using _resolve.

        self._parsed: dict[str, _ParsedEntry] = {
            name: (
                module_name,
                class_name,
                cast(_ResolvedSpecMapping, self._resolve(value)),
            )
            for module_name, class_name, name, value in parsed
        }
        # Instances will be lazily instantiated and stored in self._values
        if self._thread_safe:
            # Thread-safe mode: use mixin helpers for lock state.
            self._init_thread_safety(max_lock_attempts, lock_retry_sleep)
        else:
            # Non-thread-safe mode: use simple list for resolving stack
            self._resolving_stack: list[str] = []

    def _parse_spec_entry(
        self, key: str, value: _SpecMapping | _ConstantValue
    ) -> _UnresolvedParsedEntry | None:
        """Parse a spec entry. Returns None for constants."""
        if " " not in key:
            return None  # It's a constant

        # class wiring: "module.Class name"
        type_str, name = key.rsplit(" ", 1)
        parts = type_str.split(".")
        module_name = ".".join(parts[:-1])
        class_name = parts[-1]

        if not module_name:
            raise ValueError(
                f"invalid spec key '{key}': missing module qualification"
            )

        return (module_name, class_name, name, cast(_SpecMapping, value))

    def _resolve(self, obj: _SpecValue) -> _ResolvedValue:
        """Resolve placeholders into `_WiredRef` markers for runtime.

        Replaces strings of the form "{name}" with a `_WiredRef(name)`
        for later resolution.
        """
        if isinstance(obj, str):
            if obj.startswith("{") and obj.endswith("}"):
                ref_name = obj[1:-1]
                return _WiredRef(ref_name)
            return obj
        if isinstance(obj, dict):
            return {k: self._resolve(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._resolve(v) for v in obj]
        if isinstance(obj, tuple):
            return tuple(self._resolve(v) for v in obj)
        return obj

    def _resolve_runtime(
        self,
        o: _ResolvedValue,
        context: str | None = None,
    ) -> _RuntimeValue:
        """Resolve _WiredRef placeholders at runtime.

        This recurses into nested structures and replaces `_WiredRef` with
        the instantiated `self.<name>` value.
        """
        if isinstance(o, _WiredRef):
            # Detect when a placeholder reference points to something that
            # wasn't defined in the spec. This is an unknown placeholder
            # and should raise a friendly error.
            if o.name not in self._values and o.name not in self._parsed:
                ctx = f" while instantiating '{context}'" if context else ""
                raise UnknownPlaceholderError(
                    f"Unknown placeholder '{o.name}' referenced{ctx}."
                )
            # Membership check ensures `o.name` is known; if getattr raises
            # AttributeError it's from instance creation — let it propagate.
            # Call the accessor `self.name()` to get the runtime value.
            return cast(object, getattr(self, o.name)())
        if isinstance(o, dict):
            return {
                k: self._resolve_runtime(v, context=context)
                for k, v in o.items()
            }
        if isinstance(o, list):
            return [self._resolve_runtime(v, context=context) for v in o]
        if isinstance(o, tuple):
            return tuple(self._resolve_runtime(v, context=context) for v in o)
        return o

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
        data: _ResolvedSpecMapping,
        *,
        aio: bool = False,
        thread_safe: bool = False,
    ) -> ast.FunctionDef | ast.AsyncFunctionDef:
        """Build an AST FunctionDef for a cached accessor that returns
        ``module.class(**data)``.

        When ``aio`` is True this function will produce an
        ``ast.AsyncFunctionDef`` that awaits referenced accessors and calls
        the blocking constructor in an executor (``loop.run_in_executor``).
        When ``aio`` is False it produces a standard synchronous
        ``ast.FunctionDef``.
        """
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

        # Helper to extract `await self.<name>()` occurrences from AST
        # expressions and replace them with local variables. This lets us
        # run a synchronous lambda in `run_in_executor` without `await`
        # nodes embedded inside it.
        counter = 0

        def _replace_awaits_with_locals(node: ast.expr) -> ast.expr:
            nonlocal counter

            if isinstance(node, ast.Await):
                inner = node.value
                if (
                    isinstance(inner, ast.Call)
                    and isinstance(inner.func, ast.Attribute)
                    and isinstance(inner.func.value, ast.Name)
                    and inner.func.value.id == "self"
                ):
                    # produce a unique variable name and precompute the await
                    counter += 1
                    var_name = f"__val_{counter}"
                    assign = ast.Assign(
                        targets=[ast.Name(id=var_name, ctx=ast.Store())],
                        value=node,
                    )
                    pre_statements.append(assign)
                    return ast.Name(id=var_name, ctx=ast.Load())
                return node

            # Recurse into common composite nodes
            if isinstance(node, ast.Call):
                new_args = [_replace_awaits_with_locals(a) for a in node.args]
                new_keywords = [
                    ast.keyword(
                        arg=k.arg, value=_replace_awaits_with_locals(k.value)
                    )
                    for k in node.keywords
                ]
                return ast.Call(
                    func=node.func, args=new_args, keywords=new_keywords
                )
            if isinstance(node, ast.Dict):
                new_keys = [
                    _replace_awaits_with_locals(k) if k is not None else None
                    for k in node.keys
                ]
                new_values = [
                    _replace_awaits_with_locals(v) for v in node.values
                ]
                return ast.Dict(keys=new_keys, values=new_values)
            if isinstance(node, ast.List):
                return ast.List(
                    elts=[_replace_awaits_with_locals(e) for e in node.elts],
                    ctx=node.ctx,
                )
            if isinstance(node, ast.Tuple):
                return ast.Tuple(
                    elts=[_replace_awaits_with_locals(e) for e in node.elts],
                    ctx=node.ctx,
                )
            return node

        for key, value in data.items():
            raw_val_ast = self._astify(value, aio=aio)
            if aio:
                # Replace any awaited accessors with local precomputed
                # variables and assign all values to local variables so
                # that the executor lambda can be synchronous.
                val_ast = _replace_awaits_with_locals(raw_val_ast)
                # Use named variables for top-level keyword args to make
                # the generated code more readable and deterministic.
                var_name = f"__val_{key}"
                assign = ast.Assign(
                    targets=[ast.Name(id=var_name, ctx=ast.Store())],
                    value=val_ast,
                )
                pre_statements.append(assign)
                kw_val: ast.expr = ast.Name(id=var_name, ctx=ast.Load())
            else:
                kw_val = raw_val_ast
            kwargs.append(ast.keyword(arg=key, value=kw_val))

        # Build the actual constructor call (module.Class(**kwargs))
        call = ast.Call(func=module_attr, args=[], keywords=kwargs)

        # Cache attribute name like `_name` used to store instantiated
        # objects on `self` at runtime. The compiled accessor returns
        # `self._name` when present.
        cache_attr = f"_{name}"

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

    def __getattr__(self, name: str) -> Callable[[], _RuntimeValue] | Accessor:
        """Return an accessor callable for `name` that returns the
        instantiated object for that name when invoked.

        The returned accessor supports synchronous invocation via
        callable `wired.name()`.
        Use `await wired.aio.name()` to obtain the instantiated value
        asynchronously.
        """
        # Return cached value (constant or already instantiated)
        if name in self._values:
            # Return a callable that returns the current cached value.
            def _quick() -> _RuntimeValue:
                return self._values[name]

            return _quick

        if name not in self._parsed:
            raise AttributeError(f"no attribute '{name}'")

        self._check_circular_dependency(name)

        # Return a callable accessor object that mirrors the previous
        # synchronous behavior. For asynchronous access use `wired.aio`.
        return Accessor(self, name)

    @property
    def aio(self) -> "AioAccessor":
        """Return a wrapper object providing async accessors.

        Use `await wired.aio.name()` to obtain the instantiated value
        asynchronously. We use `aio` to avoid the reserved keyword
        `async` (so `wired.async` would be invalid syntax).
        """
        if not hasattr(self, "_aio_accessor"):
            self._aio_accessor = AioAccessor(self)
        return self._aio_accessor

    def _access_impl(self, name: str) -> _RuntimeValue:
        """Common implementation for synchronous accessors.

        This contains the former logic that lived inside the accessor
        closure and is reused by both the sync call and the async
        executor wrapper.
        """
        # Fast non-thread-safe path
        if not self._thread_safe:
            self._get_resolving_stack().append(name)
            try:
                try:
                    return self._instantiate_impl(name)
                except (UnknownPlaceholderError, CircularWiringError):
                    raise
                except WiringError as e:
                    raise WiringError(f"failed to instantiate '{name}'") from e
                except Exception as e:
                    raise WiringError(f"failed to instantiate '{name}'") from e
            finally:
                self._get_resolving_stack().pop()

        # Thread-safe mode: use the mixin's `_instantiate_attr` helper.
        stack = self._get_resolving_stack()
        stack.append(name)
        try:

            def _maker() -> _RuntimeValue:
                return self._instantiate_impl(name)

            return self._instantiate_attr(name, _maker)
        finally:
            stack.pop()

    def _check_circular_dependency(self, name: str) -> None:
        """Check for circular dependencies in the wiring graph.

        Uses either the simple list (non-thread-safe) or thread-local
        stack to detect cycles.
        """
        stack = self._get_resolving_stack()
        if name in stack:
            cycle = " -> ".join(stack + [name])
            raise CircularWiringError(
                f"Circular wiring dependency detected: {cycle}."
            )

    def _get_resolving_stack(self) -> list[str]:
        """Get or initialize the resolving stack for the current mode.

        Returns the per-thread resolving stack when `thread_safe` is True,
        otherwise returns the single shared list on `self`.
        """
        if not self._thread_safe:
            if not hasattr(self, "_resolving_stack"):
                self._resolving_stack = []
            return self._resolving_stack

        # Delegate to mixin for thread-local resolving stack
        return super()._get_resolving_stack()

    # `_get_held_locks` and `_get_attribute_lock` are provided by the
    # `CompiledThreadSafeMixin` when `thread_safe` is enabled.

    def _instantiate_impl(self, name: str) -> _RuntimeValue:
        """Import module, resolve kwargs and instantiate the class."""
        # If another thread created the instance while we were waiting,
        # return it to avoid duplicates.
        if name in self._values:
            return self._values[name]

        module_name, class_name, ins_data = self._parsed[name]
        module = importlib.import_module(module_name)
        cls = cast(  # type: ignore[explicit-any, misc]
            Callable[..., object], getattr(module, class_name)
        )

        # Build kwargs, resolving wired references to runtime objects
        kwargs: dict[str, _RuntimeValue] = {}
        for k, v in ins_data.items():
            kwargs[k] = self._resolve_runtime(v, context=name)

        instance = cls(**kwargs)
        self._values[name] = instance
        return instance

    # Thread-safety helpers are provided by CompiledThreadSafeMixin and
    # accessed via `_init_thread_safety()`, `_get_attribute_lock()`,
    # `_get_held_locks()`, `_release_held_locks()` and
    # `_instantiate_attr(name, maker)`.

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
        for module_name, _, _ in self._parsed.values():
            modules.add(module_name)
        if aio:
            modules.add("asyncio")
        if thread_safe:
            # When compiling thread_safe, import thread-safety primitives
            modules.add("apywire.thread_safety")
            modules.add("apywire.exceptions")
        for module in sorted(modules):
            if module == "apywire.thread_safety":
                # Import CompiledThreadSafeMixin from thread_safety
                body.append(
                    ast.ImportFrom(
                        module="apywire.thread_safety",
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
        for name, (module_name, class_name, data) in self._parsed.items():
            class_body.append(
                self._compile_property(
                    name,
                    module_name,
                    class_name,
                    data,
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
        # apywire.thread_safety rather than embedding helper code.
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


@final
class Accessor:
    """Callable accessor returned by `Wiring.__getattr__`.

    Accessing `wired.name` returns an `Accessor` object which is
    callable: `wired.name()` returns the instantiated object. If you
    need async access, use `await wired.aio.name()`.
    """

    def __init__(self, wiring: Wiring, name: str) -> None:
        self._wiring = wiring
        self._name = name

    def __call__(self) -> _RuntimeValue:
        return self._wiring._access_impl(self._name)


@final
class AioAccessor:
    """Wrapper used to return async callables via `wired.aio`.

    Example: ``await wired.aio.name()`` will return the requested value
    asynchronously. If ``name`` is a constant cached in ``_values`` the
    accessor returns it directly (no executor is used). Otherwise the
    synchronous instantiation is executed in a threadpool (``run_in_executor``)
    and the instance is returned.
    """

    def __init__(self, wiring: Wiring) -> None:
        self._wiring = wiring

    def __getattr__(
        self,
        name: str,
    ) -> Callable[[], Awaitable[_RuntimeValue]]:
        # If we already have a cached value (constants and already-created
        # instances), return an async function that returns it directly.
        if name in self._wiring._values:

            async def _quick() -> _RuntimeValue:
                return self._wiring._values[name]

            return _quick

        # Unknown attributes should raise like the sync accessor.
        if name not in self._wiring._parsed:
            raise AttributeError(f"no attribute '{name}'")

        async def _acall() -> _RuntimeValue:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                None, self._wiring._access_impl, name
            )

        return _acall


# `_LockUnavailableError` is imported from `apywire.thread_safety` to
# keep a single canonical definition shared between runtime and compiled
# variants. See `apywire/thread_safety.py` for the implementation.
