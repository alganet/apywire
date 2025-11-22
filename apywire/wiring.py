# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC


"""Core wiring functionality."""

from __future__ import annotations

import ast
import importlib
import threading
import time
from types import EllipsisType
from typing import (
    Callable,
    Literal,
    TypeAlias,
    cast,
)

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


class _ThreadLocalState(threading.local):
    """Thread-local state for wiring resolution.

    Attributes:
        resolving_stack: Stack of attribute names currently being resolved
                        in this thread (for circular dependency detection).
        mode: Current instantiation mode ('optimistic', 'global', or None).
        held_locks: List of locks currently held by this thread.
    """

    resolving_stack: list[str]
    mode: Literal["optimistic", "global"] | None
    held_locks: list[threading.RLock]


class WiringError(AttributeError):
    """Raised when the wiring system cannot instantiate an attribute.

    This wraps the underlying exception to provide context on which
    attribute failed to instantiate, while preserving the original
    exception as the cause.
    """


class UnknownPlaceholderError(WiringError):
    """Raised by `_resolve_runtime` when a placeholder name is not
    found in either constants (`_values`) or parsed spec entries
    (`_parsed`).
    """


class CircularWiringError(WiringError):
    """Raised when a circular wiring dependency is detected.

    This class is a `WiringError` subtype for simpler programmatic
    handling of wiring-specific failures.
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


class Wiring:
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
            # Thread-safe mode: use locks for concurrent access.
            # Use reentrant locks to enable re-entrancy while creating
            # dependent attributes.
            self._inst_lock = threading.RLock()
            # Per-thread resolving stack to detect circular dependencies.
            self._local: _ThreadLocalState = _ThreadLocalState()
            # Per-attribute locks used to increase parallelism when possible.
            self._attr_locks: dict[str, threading.RLock] = {}
            self._attr_locks_lock = threading.Lock()
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

    def _astify(self, obj: _ResolvedValue) -> ast.expr:
        """Convert a Python object (possibly a `_WiredRef`) to AST.

        Nested lists, tuples and dicts are supported. `_WiredRef` becomes
        an accessor call (`self.<name>()`) to mirror runtime behavior.
        """
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

    def _compile_property(
        self,
        name: str,
        module_name: str,
        class_name: str,
        data: _ResolvedSpecMapping,
    ) -> ast.FunctionDef:
        """Build an AST FunctionDef for a cached accessor that returns
        module.class(**data).
        """
        module_attr = ast.Attribute(
            value=ast.Name(id=module_name, ctx=ast.Load()),
            attr=class_name,
            ctx=ast.Load(),
        )
        kwargs: list[ast.keyword] = []
        for k, v in data.items():
            kwargs.append(ast.keyword(k, value=self._astify(v)))
        call = ast.Call(func=module_attr, args=[], keywords=kwargs)
        cache_attr = f"_{name}"
        return_stmt = ast.Return(
            value=ast.Attribute(
                value=ast.Name(id="self", ctx=ast.Load()),
                attr=cache_attr,
                ctx=ast.Load(),
            )
        )
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
        return func_def

    def _compile_constant_property(
        self,
        name: str,
        value: _ConstantValue,
    ) -> ast.FunctionDef:
        """Return an AST FunctionDef for an accessor that returns a
        constant value.
        """
        return_stmt = ast.Return(value=ast.Constant(value))
        func_def = ast.FunctionDef(
            name=name,
            args=_PROPERTY_ARGS,
            body=[return_stmt],
            decorator_list=[],
            returns=None,
            type_comment=None,
            type_params=[],
        )
        return func_def

    def __getattr__(self, name: str) -> Callable[[], _RuntimeValue]:
        """Return an accessor callable for `name` that returns the
        instantiated object for that name when invoked.
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

        # Create and return a bound accessor function that mirrors the
        # behavior previously implemented in __getattr__ (including
        # threading/locking behavior and exception wrapping).
        def _accessor() -> _RuntimeValue:
            # Fast non-thread-safe path
            if not self._thread_safe:
                self._get_resolving_stack().append(name)
                try:
                    try:
                        return self._instantiate_impl(name)
                    except (UnknownPlaceholderError, CircularWiringError):
                        raise
                    except WiringError as e:
                        raise WiringError(
                            f"failed to instantiate '{name}'"
                        ) from e
                    except Exception as e:
                        raise WiringError(
                            f"failed to instantiate '{name}'"
                        ) from e
                finally:
                    self._get_resolving_stack().pop()

            # Thread-safe mode: use locks and modes
            stack = self._get_resolving_stack()
            stack.append(name)
            try:
                lock = self._get_attribute_lock(name)
                mode = (
                    self._local.mode if hasattr(self._local, "mode") else None
                )

                if mode is None:
                    return self._instantiate_top_level(name, lock)

                return self._instantiate_nested(name, lock, mode)
            finally:
                stack.pop()

        return _accessor

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

        if not hasattr(self._local, "resolving_stack"):
            self._local.resolving_stack = []
        return self._local.resolving_stack

    def _get_held_locks(self) -> list[threading.RLock]:
        """Get or initialize the thread-local held locks list."""
        if not hasattr(self._local, "held_locks"):
            self._local.held_locks = []
        return self._local.held_locks

    def _get_attribute_lock(self, name: str) -> threading.RLock:
        """Get or create a per-attribute lock."""
        with self._attr_locks_lock:
            if name not in self._attr_locks:
                self._attr_locks[name] = threading.RLock()
            return self._attr_locks[name]

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

    def _instantiate_top_level(
        self,
        name: str,
        lock: threading.RLock,
    ) -> _RuntimeValue:
        # Try optimistic per-attribute lock
        if lock.acquire(blocking=False):
            try:
                return self._attempt_optimistic_instantiation(name, lock)
            except _LockUnavailable:
                # Fall back to global lock
                pass

        return self._attempt_global_instantiation(name, lock)

    def _attempt_optimistic_instantiation(
        self,
        name: str,
        lock: threading.RLock,
    ) -> _RuntimeValue:
        """Attempt optimistic per-attribute instantiation.

        Raises `_LockUnavailable` if the per-attribute lock cannot be
        acquired.
        """
        self._local.mode = "optimistic"
        held_locks = self._get_held_locks()
        held_locks.clear()
        held_locks.append(lock)

        try:
            result = self._instantiate_impl(name)
            # Success - clean up and return
            self._release_held_locks()
            self._local.mode = None
            return result
        except _LockUnavailable:
            self._release_held_locks()
            raise
        except (UnknownPlaceholderError, CircularWiringError):
            self._release_held_locks()
            raise
        except WiringError as e:
            self._release_held_locks()
            raise WiringError(f"failed to instantiate '{name}'") from e
        except Exception as e:
            self._release_held_locks()
            raise WiringError(f"failed to instantiate '{name}'") from e
        finally:
            if (
                hasattr(self._local, "mode")
                and self._local.mode == "optimistic"
            ):
                self._local.mode = None

    def _attempt_global_instantiation(
        self,
        name: str,
        lock: threading.RLock,
    ) -> _RuntimeValue:
        self._local.mode = "global"

        with self._inst_lock:
            lock.acquire()
            try:
                held_locks = self._get_held_locks()
                held_locks.clear()
                held_locks.append(lock)
                # Retry loop in case nested calls still raise
                # `_LockUnavailable` despite global mode (race). Sleep
                # briefly between attempts.
                attempts = 0
                while True:
                    try:
                        return self._instantiate_impl(name)
                    except _LockUnavailable:
                        attempts += 1
                        if attempts > self._max_lock_attempts:
                            raise WiringError(
                                f"failed to instantiate '{name}'"
                            )
                        time.sleep(self._lock_retry_sleep)
                        continue
            finally:
                self._release_held_locks()
                self._local.mode = None

    def _instantiate_nested(
        self,
        name: str,
        lock: threading.RLock,
        mode: Literal["optimistic", "global"],
    ) -> _RuntimeValue:
        if mode == "optimistic":
            # Acquire per-attribute lock non-blocking; on failure raise
            # `_LockUnavailable` to fall back to global lock mode.
            if not lock.acquire(blocking=False):
                raise _LockUnavailable()
        else:
            # In 'global' mode, acquire the per-attribute lock blocking.
            lock.acquire()

        held = self._get_held_locks()
        held.append(lock)
        try:
            return self._instantiate_impl(name)
        finally:
            # Lock remains held until the outermost caller releases it.
            pass

    def _release_held_locks(self) -> None:
        """Release locks held by the current thread in LIFO order."""
        if not hasattr(self._local, "held_locks"):
            return

        for lock in reversed(self._local.held_locks):
            lock.release()
        self._local.held_locks = []

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
        for name, (module_name, class_name, data) in self._parsed.items():
            class_body.append(
                self._compile_property(
                    name,
                    module_name,
                    class_name,
                    data,
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


class _LockUnavailable(RuntimeError):
    """Internal exception raised when a per-attribute lock cannot be acquired
    in optimistic (non-blocking) mode and we need to fall back to the
    global instantiation lock.
    """
