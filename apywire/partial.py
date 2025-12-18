# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

"""Helpers for partial construction used by compiled containers.

This module contains a small helper that compiled accessors can call to
preserve partial-construction (skeleton) semantics without depending on
`apywire.runtime` internals. It is imported only when the compiler is
configured with `allow_partial=True` so compiled output does
not include unnecessary runtime dependencies.
"""

from __future__ import annotations

import threading
from typing import Callable, List, Optional, Protocol, cast

from apywire.exceptions import CircularWiringError, PartialConstructionError


class _ContainerLike(Protocol):
    _values: dict[str, object] | None
    _resolving_stack: list[str] | None
    allow_partial: bool


def _compiled_instantiate_with_partial(
    container: object,
    name: str,
    constructor_callable: Callable[[], object],
    expected_cls: type,
    is_factory: bool,
) -> object:  # pragma: no cover
    # Exercised indirectly via compiler integration
    """Helper used by compiled accessors to support partial construction.

    See runtime._compiled_instantiate_with_partial for detailed semantics.
    """
    # Ensure resolving stack exists
    stack_existing: object = getattr(container, "_resolving_stack", None)
    if isinstance(stack_existing, list):
        stack = cast(List[str], stack_existing)
    else:
        stack = []
        try:
            setattr(container, "_resolving_stack", stack)
        except Exception:  # pragma: no cover - defensive
            pass

    # Detect cycle; cast container for typing
    container_obj = cast(_ContainerLike, container)
    if name in stack:
        if not container_obj.allow_partial:
            msg = (
                "Circular wiring dependency detected: "
                + " -> ".join(stack)
                + " -> "
                + name
            )
            raise CircularWiringError(msg)
        # Allocate skeleton and set partial markers
        try:
            # Use __new__ to allocate without invoking __init__
            new_fn = cast(Callable[[type], object], expected_cls.__new__)
            skeleton: object = new_fn(expected_cls)
        except Exception as e:
            raise PartialConstructionError(
                "failed to allocate skeleton for %r: %s" % (expected_cls, e)
            ) from e
        try:
            setattr(skeleton, "_apywire_partial", True)
            setattr(skeleton, "_apywire_event", threading.Event())
            setattr(skeleton, "_apywire_failure", None)
        except Exception:  # pragma: no cover - defensive
            raise PartialConstructionError(
                f"type {expected_cls} cannot be skeletonized"
            )
        # Cache and return skeleton placeholder
        values = cast(
            Optional[dict[str, object]],
            getattr(container_obj, "_values", None),
        )
        if values is not None:
            values[name] = skeleton
        else:
            setattr(container, "_" + name, skeleton)
        return skeleton

    stack.append(name)
    try:
        # If a skeleton was inserted by nested resolution, bind to it
        cached: Optional[object] = None
        values = cast(
            Optional[dict[str, object]],
            getattr(container_obj, "_values", None),
        )
        if values is not None:
            cached = values.get(name)
        else:
            cached = cast(
                Optional[object], getattr(container, "_" + name, None)
            )

        if cached is not None and cast(
            bool, getattr(cached, "_apywire_partial", False)
        ):
            skeleton = cached
            try:
                if is_factory:
                    # Temporary override of __new__
                    orig_new: Optional[object] = getattr(
                        expected_cls, "__new__", None
                    )

                    def _tmp_new(
                        _cls: type, *a: object, **k: object
                    ) -> object:
                        return skeleton

                    setattr(expected_cls, "__new__", _tmp_new)
                    try:
                        ret: object = constructor_callable()
                    finally:
                        if orig_new is None:
                            try:
                                delattr(expected_cls, "__new__")
                            except Exception:  # pragma: no cover - defensive
                                pass
                        else:
                            try:
                                setattr(expected_cls, "__new__", orig_new)
                            except Exception:
                                pass

                    if ret is not skeleton:
                        exc = PartialConstructionError(
                            "factory for %r returned a different instance "
                            "than the skeleton" % (name,)
                        )
                        try:
                            setattr(skeleton, "_apywire_failure", exc)
                            setattr(skeleton, "_apywire_partial", False)
                            ev = cast(
                                Optional[threading.Event],
                                getattr(skeleton, "_apywire_event", None),
                            )
                            if ev is not None:
                                ev.set()
                        finally:
                            values_cleanup = cast(
                                Optional[dict[str, object]],
                                getattr(container_obj, "_values", None),
                            )
                            if (
                                values_cleanup is not None
                                and values_cleanup.get(name) is skeleton
                            ):
                                del values_cleanup[name]
                        raise exc
                    # Success
                    try:
                        setattr(skeleton, "_apywire_partial", False)
                        ev = cast(
                            Optional[threading.Event],
                            getattr(skeleton, "_apywire_event", None),
                        )
                        if ev is not None:
                            ev.set()
                    except Exception:  # pragma: no cover - defensive
                        pass
                    return skeleton
                else:
                    # Direct init
                    try:
                        init_attr: object = getattr(
                            expected_cls, "__init__", object.__init__
                        )
                        direct_init = cast(
                            Callable[[object], object | None],
                            init_attr,
                        )
                        direct_init(skeleton)
                    except Exception as e:
                        exc = PartialConstructionError(
                            "failed to initialize skeleton for %r: %s"
                            % (name, e)
                        )
                        try:
                            setattr(skeleton, "_apywire_failure", exc)
                            setattr(skeleton, "_apywire_partial", False)
                            ev = cast(
                                Optional[threading.Event],
                                getattr(skeleton, "_apywire_event", None),
                            )
                            if ev is not None:
                                ev.set()
                        finally:
                            values_cleanup = cast(
                                Optional[dict[str, object]],
                                getattr(container_obj, "_values", None),
                            )
                            if (
                                values_cleanup is not None
                                and values_cleanup.get(name) is skeleton
                            ):
                                del values_cleanup[name]
                        raise exc from e
                    try:
                        setattr(skeleton, "_apywire_partial", False)
                        ev = cast(
                            Optional[threading.Event],
                            getattr(skeleton, "_apywire_event", None),
                        )
                        if ev is not None:
                            ev.set()
                    except Exception:  # pragma: no cover - defensive
                        pass
                    return skeleton
            except PartialConstructionError:
                raise
            except Exception as e:
                exc = PartialConstructionError(
                    f"partial construction failed for '{name}': {e}"
                )
                try:
                    setattr(skeleton, "_apywire_failure", exc)
                    setattr(skeleton, "_apywire_partial", False)
                    ev = cast(
                        Optional[threading.Event],
                        getattr(skeleton, "_apywire_event", None),
                    )
                    if ev is not None:
                        ev.set()
                finally:
                    values_cleanup = cast(
                        Optional[dict[str, object]],
                        getattr(container_obj, "_values", None),
                    )
                    if (
                        values_cleanup is not None
                        and values_cleanup.get(name) is skeleton
                    ):
                        del values_cleanup[name]
                raise exc from e

        # No skeleton present; call constructor normally
        ret = constructor_callable()
        # If nested resolution inserted a skeleton, validate and finalize it.
        cached_now: Optional[object] = None
        values_now = cast(
            Optional[dict[str, object]],
            getattr(container_obj, "_values", None),
        )
        if values_now is not None:
            cached_now = values_now.get(name)
        else:
            cached_now = cast(
                Optional[object], getattr(container, "_" + name, None)
            )
        if cached_now is not None and cast(
            bool, getattr(cached_now, "_apywire_partial", False)
        ):
            skeleton = cached_now
            if ret is not skeleton:
                # Retry factory with __new__ overridden to return skeleton
                if is_factory:
                    orig_new = cast(
                        object, getattr(expected_cls, "__new__", None)
                    )

                    def _tmp_new(
                        _cls: type, *a: object, **k: object
                    ) -> object:
                        return skeleton

                    setattr(expected_cls, "__new__", _tmp_new)
                    try:
                        retry_ret: object = constructor_callable()
                    finally:
                        if orig_new is None:
                            try:
                                delattr(expected_cls, "__new__")
                            except Exception:
                                pass
                        else:
                            try:
                                setattr(expected_cls, "__new__", orig_new)
                            except Exception:
                                pass

                    if retry_ret is not skeleton:
                        exc = PartialConstructionError(
                            "factory for %r returned a different instance "
                            "than the skeleton" % (name,)
                        )
                        try:
                            setattr(skeleton, "_apywire_failure", exc)
                            setattr(skeleton, "_apywire_partial", False)
                            ev = cast(
                                Optional[threading.Event],
                                getattr(skeleton, "_apywire_event", None),
                            )
                            if ev is not None:
                                ev.set()
                        finally:
                            values_cleanup = cast(
                                Optional[dict[str, object]],
                                getattr(container_obj, "_values", None),
                            )
                            if (
                                values_cleanup is not None
                                and values_cleanup.get(name) is skeleton
                            ):
                                del values_cleanup[name]
                        raise exc
                    # Success on retry
                    try:
                        setattr(skeleton, "_apywire_partial", False)
                        ev = cast(
                            Optional[threading.Event],
                            getattr(skeleton, "_apywire_event", None),
                        )
                        if ev is not None:
                            ev.set()
                    except Exception:  # pragma: no cover - defensive
                        pass
                    return skeleton
                else:
                    exc = PartialConstructionError(
                        "factory for %r returned a different instance "
                        "than the skeleton" % (name,)
                    )
                    try:
                        setattr(skeleton, "_apywire_failure", exc)
                        setattr(skeleton, "_apywire_partial", False)
                        ev = cast(
                            Optional[threading.Event],
                            getattr(skeleton, "_apywire_event", None),
                        )
                        if ev is not None:
                            ev.set()
                    finally:
                        values_cleanup = cast(
                            Optional[dict[str, object]],
                            getattr(container_obj, "_values", None),
                        )
                        if (
                            values_cleanup is not None
                            and values_cleanup.get(name) is skeleton
                        ):
                            del values_cleanup[name]
                    raise exc
            else:
                try:
                    setattr(skeleton, "_apywire_partial", False)
                    ev = cast(
                        Optional[threading.Event],
                        getattr(skeleton, "_apywire_event", None),
                    )
                    if ev is not None:
                        ev.set()
                except Exception:  # pragma: no cover - defensive
                    pass
            return skeleton
        return ret
    finally:
        stack.pop()
