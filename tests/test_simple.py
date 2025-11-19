# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
# SPDX-License-Identifier: ISC

import datetime
from typing import Protocol

import apywire


def test_simple_load_constructor_args() -> None:
    spec: apywire.Spec = {
        "datetime.datetime yearsAgo": {
            "day": 13,
            "month": 12,
            "year": 2003,
        }
    }
    wired: apywire.Wired[object] = apywire.wire(spec)
    instance = wired.yearsAgo
    assert isinstance(instance, datetime.datetime)
    assert instance.year == 2003
    assert instance.month == 12
    assert instance.day == 13


def test_simple_raise_on_nonexistent_wired_attribute() -> None:
    try:
        apywire.wire({}).nonexistent
        assert False, "Should have raised AttributeError"
    except AttributeError as e:
        assert "no attribute 'nonexistent'" in str(e)


def test_simple_compile_constructor_args() -> None:
    spec: apywire.Spec = {
        "datetime.datetime birthday": {
            "day": 25,
            "month": 12,
            "year": 1990,
        }
    }

    pythonCode = apywire.compile(spec)
    assert (
        """import datetime
class Compiled:
    @property
    def birthday(self):
        return datetime.datetime(day=25, month=12, year=1990)
compiled = Compiled()"""
        in pythonCode
    )

    class MockHasBirthday(Protocol):
        birthday: datetime.datetime

    execd: dict[str, MockHasBirthday] = {}
    exec(pythonCode, execd)
    compiled = execd["compiled"]

    instance = compiled.birthday
    assert isinstance(instance, datetime.datetime)
    assert instance.year == 1990
    assert instance.month == 12
    assert instance.day == 25
