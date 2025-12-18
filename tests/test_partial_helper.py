# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

import asyncio
import threading
from typing import Callable, cast

import pytest

import apywire
from apywire.exceptions import CircularWiringError, PartialConstructionError
from apywire.partial import _compiled_instantiate_with_partial
from apywire.runtime import Accessor, AioAccessor, _Constructor


class _DummyContainer:
    def __init__(
        self,
        *,
        allow_partial: bool = True,
        values: dict[str, object] | None = None,
        stack: list[str] | None = None,
    ) -> None:
        self._values = values
        self._resolving_stack = stack
        self.allow_partial = allow_partial
        self._item: object | None = None


class _SimpleFactory:
    _apywire_partial: bool
    _apywire_event: threading.Event
    _apywire_failure: Exception | None

    def __init__(self) -> None:
        self.created = True

    @classmethod
    def build(cls) -> "_SimpleFactory":
        return cls()


class _ExplodingInit:
    _apywire_partial: bool
    _apywire_event: threading.Event
    _apywire_failure: Exception | None

    def __init__(self) -> None:
        raise RuntimeError("boom")


class _NoAttrs:
    __slots__ = ()

    def __call__(
        self, *args: object, **kwargs: object
    ) -> "_NoAttrs":  # pragma: no cover
        return self


class _LockedSlots:
    __slots__ = ()

    def __new__(cls) -> "_LockedSlots":
        return super().__new__(cls)


class _Skeleton:
    def __init__(self, failure: Exception | None = None) -> None:
        self._apywire_partial = True
        self._apywire_event = threading.Event()
        self._apywire_failure = failure


def _make_skeleton(
    ready: bool = False, failure: Exception | None = None
) -> _Skeleton:
    skeleton = _Skeleton(failure)
    if ready:
        skeleton._apywire_event.set()
        skeleton._apywire_partial = False
    return skeleton


def test_compiled_partial_rejects_circular_without_opt_in() -> None:
    container = _DummyContainer(allow_partial=False, values={}, stack=["item"])

    with pytest.raises(CircularWiringError):
        _compiled_instantiate_with_partial(
            container,
            "item",
            lambda: _SimpleFactory.build(),
            _SimpleFactory,
            True,
        )


def test_compiled_partial_allocates_and_caches_skeleton() -> None:
    container = _DummyContainer(values={}, stack=["item"])

    skeleton = _compiled_instantiate_with_partial(
        container,
        "item",
        _SimpleFactory.build,
        _SimpleFactory,
        True,
    )

    assert isinstance(skeleton, _SimpleFactory)
    assert container._values == {"item": skeleton}
    assert skeleton._apywire_partial is True
    assert skeleton._apywire_event.is_set() is False

    container._resolving_stack = []
    finalized = _compiled_instantiate_with_partial(
        container,
        "item",
        _SimpleFactory.build,
        _SimpleFactory,
        True,
    )

    assert finalized is skeleton
    assert skeleton._apywire_partial is False
    assert skeleton._apywire_event.is_set() is True


def test_compiled_partial_factory_mismatch_cleans_up() -> None:
    container = _DummyContainer(values={}, stack=["item"])
    _compiled_instantiate_with_partial(
        container,
        "item",
        _SimpleFactory.build,
        _SimpleFactory,
        True,
    )
    container._resolving_stack = []

    with pytest.raises(PartialConstructionError):
        _compiled_instantiate_with_partial(
            container,
            "item",
            lambda: object(),
            _SimpleFactory,
            True,
        )

    assert container._values == {}


def test_compiled_partial_direct_init_failure_removes_placeholder() -> None:
    container = _DummyContainer(values={}, stack=["item"])
    _compiled_instantiate_with_partial(
        container,
        "item",
        _ExplodingInit,
        _ExplodingInit,
        False,
    )
    container._resolving_stack = []

    with pytest.raises(PartialConstructionError):
        _compiled_instantiate_with_partial(
            container,
            "item",
            _ExplodingInit,
            _ExplodingInit,
            False,
        )

    assert container._values == {}


def test_compiled_partial_direct_init_success_with_attr_cache() -> None:
    container = _DummyContainer(values=None, stack=["item"])
    _compiled_instantiate_with_partial(
        container,
        "item",
        _SimpleFactory,
        _SimpleFactory,
        False,
    )
    container._resolving_stack = []

    result = _compiled_instantiate_with_partial(
        container,
        "item",
        _SimpleFactory,
        _SimpleFactory,
        False,
    )

    assert isinstance(result, _SimpleFactory)
    assert result is container._item
    assert result._apywire_partial is False


def test_compiled_partial_new_failure_raises() -> None:
    container = _DummyContainer(values={}, stack=["item"])

    class NewBoom:
        def __new__(cls) -> "NewBoom":
            raise RuntimeError("nope")

    with pytest.raises(PartialConstructionError):
        _compiled_instantiate_with_partial(
            container,
            "item",
            lambda: NewBoom(),
            NewBoom,
            False,
        )


def test_compiled_partial_marker_injection_failure() -> None:
    container = _DummyContainer(values={}, stack=["item"])

    with pytest.raises(PartialConstructionError):
        _compiled_instantiate_with_partial(
            container,
            "item",
            _LockedSlots,
            _LockedSlots,
            False,
        )


def test_compiled_partial_cached_factory_generic_error_cleans_up() -> None:
    container = _DummyContainer(values={}, stack=["item"])
    _compiled_instantiate_with_partial(
        container,
        "item",
        _SimpleFactory.build,
        _SimpleFactory,
        True,
    )
    container._resolving_stack = []

    def _raise() -> object:
        raise RuntimeError("bang")

    with pytest.raises(PartialConstructionError):
        _compiled_instantiate_with_partial(
            container,
            "item",
            _raise,
            _SimpleFactory,
            True,
        )

    assert container._values == {}


def test_compiled_partial_late_skeleton_mismatch_raises() -> None:
    container = _DummyContainer(values={}, stack=[])
    late_skeleton = _make_skeleton()
    container._values = {}

    def _constructor() -> object:
        values = container._values
        assert values is not None
        values["item"] = late_skeleton
        return _SimpleFactory()

    with pytest.raises(PartialConstructionError):
        _compiled_instantiate_with_partial(
            container,
            "item",
            _constructor,
            _SimpleFactory,
            False,
        )

    assert container._values == {}


def test_compiled_partial_normal_instantiation_without_skeleton() -> None:
    container = _DummyContainer(values={}, stack=[])
    marker = object()

    ret = _compiled_instantiate_with_partial(
        container,
        "item",
        lambda: marker,
        _SimpleFactory,
        False,
    )

    assert ret is marker


def test_runtime_skeletonize_type_errors_on_new_failure() -> None:
    class NewFails:
        def __new__(cls) -> "NewFails":
            raise RuntimeError("fail new")

        def __call__(self, *args: object, **kwargs: object) -> object:
            raise RuntimeError("never called")

    wiring = apywire.Wiring({})

    bad_ctor = cast(_Constructor, NewFails)

    with pytest.raises(PartialConstructionError):
        wiring._skeletonize_type(bad_ctor)


def test_runtime_skeletonize_type_errors_when_markers_forbidden() -> None:
    wiring = apywire.Wiring({})

    ctor = cast(_Constructor, _NoAttrs)

    with pytest.raises(PartialConstructionError):
        wiring._skeletonize_type(ctor)


def test_runtime_finalize_records_failure_and_signals_event() -> None:
    wiring = apywire.Wiring({})
    skeleton = _make_skeleton()
    failure = ValueError("bad")

    wiring._finalize_skeleton(skeleton, failure)

    assert skeleton._apywire_failure is failure
    assert skeleton._apywire_partial is False
    assert skeleton._apywire_event.is_set()


def test_accessor_waits_and_raises_failure() -> None:
    wiring = apywire.Wiring({})
    skeleton = _make_skeleton(failure=RuntimeError("fail"))
    skeleton._apywire_event.set()
    wiring._values["item"] = skeleton
    accessor = Accessor(wiring, "item")

    with pytest.raises(RuntimeError):
        accessor()


def test_aio_accessor_waits_and_propagates_failure() -> None:
    wiring = apywire.Wiring({})
    skeleton = _make_skeleton(failure=RuntimeError("fail"))
    skeleton._apywire_event.set()
    wiring._values["item"] = skeleton
    aio_accessor = AioAccessor(wiring)

    async def _call() -> None:
        await aio_accessor.item()

    with pytest.raises(RuntimeError):
        asyncio.run(_call())


@pytest.mark.parametrize("constructor", [int, lambda: 42])
def test_compiled_partial_handles_plain_construction(
    constructor: Callable[[], object],
) -> None:
    container = _DummyContainer(values={}, stack=[])

    result = _compiled_instantiate_with_partial(
        container,
        "plain",
        constructor,
        int,
        False,
    )

    assert result is not None
