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
    COMPILED_CLASS_NAME,
    DEFAULT_LOCK_RETRY_SLEEP,
    DEFAULT_MAX_LOCK_ATTEMPTS,
    PLACEHOLDER_REGEX,
    SPEC_EMIT_NAME,
    SYNTHETIC_CONST,
)
from apywire.wiring import (
    Spec,
    WiringBase,
    _AioWiredRef,
    _ConstantValue,
    _ResolvedSpecMapping,
    _ResolvedValue,
    _SpecValue,
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

    _spec: Spec

    def __init__(
        self,
        spec: Spec,
        *,
        thread_safe: bool = False,
        max_lock_attempts: int = DEFAULT_MAX_LOCK_ATTEMPTS,
        lock_retry_sleep: float = DEFAULT_LOCK_RETRY_SLEEP,
    ) -> None:
        """Initialize a compiler, keeping the source spec.

        `_parsed`/`_values` are a lossy decomposition of the spec, so the
        source is kept for `compile(emit_spec=True)`. It lives here and
        not on `WiringBase` because the runtime container resolves
        unknown attributes as wired entries -- an attribute there would
        shadow an entry of the same name, and every private name it holds
        is a name a spec can no longer use.
        """
        super().__init__(
            spec,
            thread_safe=thread_safe,
            max_lock_attempts=max_lock_attempts,
            lock_retry_sleep=lock_retry_sleep,
        )
        self._spec = dict(spec)

    @property
    def spec(self) -> Spec:
        """The source spec this compiler was built from.

        A shallow copy: the entries themselves are shared, so treat it as
        read-only.
        """
        return dict(self._spec)

    def _astify(self, obj: _ResolvedValue | _SpecValue) -> ast.expr:
        """Convert a Python object (possibly a `_WiredRef`) to AST.

        Nested lists, tuples and dicts are supported. `_WiredRef` becomes
        an accessor call (`self.<name>()`) to mirror runtime behavior.

        `_AioWiredRef` becomes ``self.aio.<name>`` (an async accessor
        attribute access, no call).

        A *source* spec value carries no refs -- placeholders are still
        plain strings at that point -- so this also emits the spec
        literal for `emit_spec`, where `"{name}"` must stay a string
        rather than become an accessor call.
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

    def _validate_emittable(self) -> None:
        """Reject a spec that cannot be emitted as a literal.

        A spec parsed from TOML/JSON/INI is always literal data, but one
        built in Python may hold arbitrary objects, which have no source
        representation.

        Raises:
            ValueError: If a value is not literal, or if the spec wires a
                module named `spec` (the emitted assignment would shadow
                the module's own import).
        """
        for key, value in self._spec.items():
            if not self._is_spec_constant(value):
                raise ValueError(
                    f"cannot emit spec: the value for key '{key}' is not "
                    f"a literal"
                )

        for entry in self._parsed.values():
            root = entry.module_name.split(".")[0]
            if root == SPEC_EMIT_NAME:
                raise ValueError(
                    f"cannot emit spec: the wired module "
                    f"'{entry.module_name}' would be shadowed by the "
                    f"emitted '{SPEC_EMIT_NAME}' assignment"
                )

    def _compile_spec_source(self) -> str:
        """Render the module-level ``spec = {...}`` assignment as source.

        Written one entry per line rather than unparsed as a single
        expression: a compiled defaults module is a committed artifact, so
        changing one default should produce a one-line diff, not rewrite a
        two-thousand-character line.

        Each entry still goes through `ast.unparse`, which is the only
        thing that reliably round-trips every literal a spec can hold --
        ``pprint`` would render ``inf`` and ``nan`` as bare names that do
        not evaluate.
        """
        lines = [f"{SPEC_EMIT_NAME} = {{"]
        for key, value in self._spec.items():
            key_src = ast.unparse(ast.Constant(key))
            value_src = ast.unparse(self._astify(value))
            lines.append(f"    {key_src}: {value_src},")
        lines.append("}")
        return "\n".join(lines)

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
            if_stmt = ast.If(test=has_check, body=[assign_cache], orelse=[])
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
            assign_cache = self._create_cache_assignment(cache_attr, call_inst)
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

    def _astify_interpolated_string(self, template: str) -> ast.expr:
        """Build an AST f-string from a template with placeholders.

        Turns ``"Hello {name}"`` into ``f"Hello {str(self.name())}"``.
        Each ``{ref}`` becomes a ``FormattedValue`` calling the
        accessor and converting to ``str()``.
        """
        parts: list[ast.expr | ast.Constant] = []
        last_end = 0
        for match in PLACEHOLDER_REGEX.finditer(template):
            # Add literal text before this placeholder
            if match.start() > last_end:
                parts.append(ast.Constant(template[last_end : match.start()]))
            # Add formatted value: str(self.name())
            ref_name = match.group(1)
            accessor_call = ast.Call(
                func=ast.Attribute(
                    value=ast.Name(id="self", ctx=ast.Load()),
                    attr=ref_name,
                    ctx=ast.Load(),
                ),
                args=[],
                keywords=[],
            )
            str_call = ast.Call(
                func=ast.Name(id="str", ctx=ast.Load()),
                args=[accessor_call],
                keywords=[],
            )
            parts.append(
                ast.FormattedValue(
                    value=str_call,
                    conversion=-1,
                    format_spec=None,
                )
            )
            last_end = match.end()
        # Add trailing literal
        if last_end < len(template):
            parts.append(ast.Constant(template[last_end:]))
        return ast.JoinedStr(values=parts)

    def _compile_promoted_constant(
        self,
        name: str,
        data: _ResolvedValue,
        *,
        thread_safe: bool = False,
    ) -> ast.FunctionDef:
        """Build an AST FunctionDef for an auto-promoted constant.

        Auto-promoted constants are values (strings, lists, dicts)
        that reference wired objects via placeholders. They are
        compiled as cached accessors that resolve wired refs at
        call time.
        """
        if isinstance(data, str):
            value_expr = self._astify_interpolated_string(data)
        else:
            value_expr = self._astify(data)
        cache_attr = f"{CACHE_ATTR_PREFIX}{name}"
        has_check = self._create_cache_check(cache_attr)
        return_stmt = self._create_return_statement(cache_attr)

        if not thread_safe:
            assign_cache = self._create_cache_assignment(
                cache_attr, value_expr
            )
            return ast.FunctionDef(
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
        else:
            maker = self._create_lambda_function(value_expr)
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
            return ast.FunctionDef(
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

    def compile(
        self,
        *,
        aio: bool = False,
        thread_safe: bool = False,
        emit_spec: bool = False,
    ) -> str:
        """Compiles the Spec into a string containing Python code.

        Args:
            aio: If True, keep sync ``def`` accessors AND add an
                ``.aio`` cached property (``CompiledAio`` wrapper).
                ``{aio.name}`` placeholders resolve to
                ``self.aio.name`` (async accessor attribute access).
            thread_safe: If True, generate thread-safe accessors using
                ``ThreadSafeMixin``.
            emit_spec: If True, also emit the source spec as a
                module-level ``spec`` dict, so the compiled container can
                be overlaid (see `merge_specs`) and re-wired at runtime.

        Returns:
            A string containing the Python source for the compiled
            `Compiled` container.

        Raises:
            ValueError: If ``emit_spec`` is set and the spec cannot be
                emitted as a literal.
        """
        if emit_spec:
            self._validate_emittable()

        # Build AST for the module
        body: list[ast.stmt] = []

        # Add import statements
        modules = set()
        for module_name, _, _, _ in self._parsed.values():
            # Skip the synthetic __sconst__ module (SYNTHETIC_CONST)
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
                self._create_cache_assignment(cache_attr, ast.Constant(cvalue))
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
            if (
                entry.module_name == SYNTHETIC_CONST
                and entry.class_name == "str"
            ):
                # Auto-promoted constant with wired refs.
                # Compile as a cached accessor that resolves refs.
                class_body.append(
                    self._compile_promoted_constant(
                        name,
                        entry.data,
                        thread_safe=thread_safe,
                    )
                )
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
            name=COMPILED_CLASS_NAME,
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
                func=ast.Name(id=COMPILED_CLASS_NAME, ctx=ast.Load()),
                args=[],
                keywords=[],
            ),
        )
        body.append(assign)

        # Create module AST
        module_ast = ast.Module(body=body, type_ignores=[])
        ast.fix_missing_locations(module_ast)

        code = ast.unparse(module_ast)
        if emit_spec:
            code = self._splice_spec_source(code)
        return code

    def _splice_spec_source(self, code: str) -> str:
        """Insert the spec literal between the imports and the container.

        Spliced as text rather than unparsed with the rest of the module,
        so it can be written one entry per line (see
        `_compile_spec_source`). It goes above `class Compiled` so a
        consumer can read the spec without instantiating anything.
        """
        lines = code.split("\n")
        at = next(
            i
            for i, line in enumerate(lines)
            if line.startswith(f"class {COMPILED_CLASS_NAME}")
        )
        spec_lines = self._compile_spec_source().split("\n")
        return "\n".join([*lines[:at], *spec_lines, "", *lines[at:]])
