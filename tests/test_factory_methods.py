# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

import datetime
import sys
from types import ModuleType
from typing import Protocol

import black

import apywire

THREE_INDENTS = 12
BLACK_MODE = black.FileMode(line_length=79 - THREE_INDENTS)


def test_factory_method_runtime_simple() -> None:
    """Test factory method with simple arguments at runtime."""
    spec: apywire.Spec = {
        "datetime.datetime myInstance.fromtimestamp": {
            0: 1234567890,
        },
    }
    wired: apywire.Wiring = apywire.Wiring(spec, thread_safe=False)
    instance = wired.myInstance()
    assert isinstance(instance, datetime.datetime)
    # fromtimestamp creates a datetime from a Unix timestamp
    expected = datetime.datetime.fromtimestamp(1234567890)
    assert instance == expected


def test_factory_method_runtime_with_kwargs() -> None:
    """Test factory method with keyword arguments at runtime."""

    class Product:
        def __init__(self, name: str, price: float) -> None:
            self.name = name
            self.price = price

        @classmethod
        def from_dict(cls, data: dict[str, object]) -> "Product":
            name_val: str = str(data["name"])
            price_val = data["price"]
            price_float: float
            if isinstance(price_val, (int, float)):
                price_float = float(price_val)
            else:
                price_float = float(str(price_val))
            return cls(name=name_val, price=price_float)

    class MockModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("product_module")
            self.Product = Product

    mod = MockModule()
    sys.modules["product_module"] = mod
    try:
        spec: apywire.Spec = {
            "product_module.Product myProduct.from_dict": {
                "data": {"name": "Widget", "price": 19.99},
            },
        }
        wired: apywire.Wiring = apywire.Wiring(spec, thread_safe=False)
        instance = wired.myProduct()
        assert isinstance(instance, Product)
        assert instance.name == "Widget"
        assert instance.price == 19.99
    finally:
        if "product_module" in sys.modules:
            del sys.modules["product_module"]


def test_factory_method_compile_simple() -> None:
    """Test that factory methods compile correctly."""
    spec: apywire.Spec = {
        "datetime.datetime myInstance.fromtimestamp": {
            0: 1234567890,
        },
    }

    python_code = apywire.WiringCompiler(spec, thread_safe=False).compile()
    python_code = black.format_str(python_code, mode=BLACK_MODE)

    # The compiled code should call datetime.datetime.fromtimestamp
    assert "datetime.datetime.fromtimestamp" in python_code

    class CompiledProt(Protocol):
        def myInstance(self) -> datetime.datetime: ...

    # Execute the compiled code
    execd: dict[str, CompiledProt] = {}
    exec(python_code, execd)

    compiled: CompiledProt = execd["compiled"]
    instance = compiled.myInstance()
    assert isinstance(instance, datetime.datetime)
    expected = datetime.datetime.fromtimestamp(1234567890)
    assert instance == expected


def test_factory_method_with_placeholder() -> None:
    """Test factory method with placeholder references."""

    class Config:
        def __init__(self, value: str) -> None:
            self.value = value

    class Service:
        def __init__(self, config: Config) -> None:
            self.config = config

        @classmethod
        def from_config(cls, cfg: Config) -> "Service":
            return cls(config=cfg)

    class MockModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("service_module")
            self.Config = Config
            self.Service = Service

    mod = MockModule()
    sys.modules["service_module"] = mod
    try:
        spec: apywire.Spec = {
            "service_module.Config myConfig": {"value": "test"},
            "service_module.Service myService.from_config": {
                "cfg": "{myConfig}",
            },
        }

        # Test runtime
        wired: apywire.Wiring = apywire.Wiring(spec, thread_safe=False)
        service_instance = wired.myService()
        assert isinstance(service_instance, Service)
        assert service_instance.config.value == "test"
        # Verify singleton behavior
        assert service_instance.config is wired.myConfig()

        # Test compilation
        python_code = apywire.WiringCompiler(spec, thread_safe=False).compile()
        assert "Service.from_config" in python_code

        class CompiledProt(Protocol):
            def myConfig(self) -> Config: ...
            def myService(self) -> Service: ...

        execd: dict[str, CompiledProt] = {}
        exec(python_code, execd)

        compiled: CompiledProt = execd["compiled"]
        compiled_service = compiled.myService()
        assert isinstance(compiled_service, Service)
        assert compiled_service.config.value == "test"
        assert compiled_service.config is compiled.myConfig()
    finally:
        if "service_module" in sys.modules:
            del sys.modules["service_module"]


def test_factory_method_static_method() -> None:
    """Test factory method with static method."""

    class Calculator:
        def __init__(self, result: int) -> None:
            self.result = result

        @staticmethod
        def create_with_sum(a: int, b: int) -> "Calculator":
            return Calculator(result=a + b)

    class MockModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("calc_module")
            self.Calculator = Calculator

    mod = MockModule()
    sys.modules["calc_module"] = mod
    try:
        spec: apywire.Spec = {
            "calc_module.Calculator myCalc.create_with_sum": {
                "a": 10,
                "b": 20,
            },
        }

        # Test runtime
        wired: apywire.Wiring = apywire.Wiring(spec, thread_safe=False)
        calc_instance = wired.myCalc()
        assert isinstance(calc_instance, Calculator)
        assert calc_instance.result == 30

        # Test compilation
        python_code = apywire.WiringCompiler(spec, thread_safe=False).compile()
        assert "Calculator.create_with_sum" in python_code

        class CompiledProt(Protocol):
            def myCalc(self) -> Calculator: ...

        execd: dict[str, CompiledProt] = {}
        exec(python_code, execd)

        compiled: CompiledProt = execd["compiled"]
        compiled_calc = compiled.myCalc()
        assert isinstance(compiled_calc, Calculator)
        assert compiled_calc.result == 30
    finally:
        if "calc_module" in sys.modules:
            del sys.modules["calc_module"]


def test_factory_method_async_accessor() -> None:
    """Test factory method with async accessor."""
    import asyncio

    spec: apywire.Spec = {
        "datetime.datetime myInstance.fromtimestamp": {
            0: 1234567890,
        },
    }
    wired: apywire.Wiring = apywire.Wiring(spec, thread_safe=False)

    async def get() -> object:
        return await wired.aio.myInstance()

    instance = asyncio.run(get())
    assert isinstance(instance, datetime.datetime)
    expected = datetime.datetime.fromtimestamp(1234567890)
    assert instance == expected
    # Verify singleton behavior with sync accessor
    assert instance is wired.myInstance()


def test_factory_method_compile_async() -> None:
    """Test factory method compilation with async mode."""
    spec: apywire.Spec = {
        "datetime.datetime myInstance.fromtimestamp": {
            0: 1234567890,
        },
    }

    python_code = apywire.WiringCompiler(spec, thread_safe=False).compile(
        aio=True
    )
    python_code = black.format_str(python_code, mode=BLACK_MODE)

    # The compiled code should call datetime.datetime.fromtimestamp
    assert "datetime.datetime.fromtimestamp" in python_code
    assert "async def myInstance" in python_code

    # Execute and test the compiled async code
    import asyncio

    class CompiledProt(Protocol):
        async def myInstance(self) -> datetime.datetime: ...

    execd: dict[str, CompiledProt] = {}
    exec(python_code, execd)

    compiled: CompiledProt = execd["compiled"]

    async def get() -> datetime.datetime:
        return await compiled.myInstance()

    instance = asyncio.run(get())
    assert isinstance(instance, datetime.datetime)
    expected = datetime.datetime.fromtimestamp(1234567890)
    assert instance == expected


def test_regular_constructor_still_works() -> None:
    """Ensure regular constructor calls still work without factory methods."""
    spec: apywire.Spec = {
        "datetime.datetime myInstance": {
            "year": 2023,
            "month": 11,
            "day": 24,
        },
    }

    # Test runtime
    wired: apywire.Wiring = apywire.Wiring(spec, thread_safe=False)
    instance = wired.myInstance()
    assert isinstance(instance, datetime.datetime)
    assert instance.year == 2023
    assert instance.month == 11
    assert instance.day == 24

    # Test compilation
    python_code = apywire.WiringCompiler(spec, thread_safe=False).compile()
    assert "datetime.datetime(" in python_code
    assert ".fromtimestamp" not in python_code


def test_nested_factory_methods_raises_error() -> None:
    """Test that nested factory methods raise a clear error."""
    try:
        apywire.Wiring(
            {
                "datetime.datetime instance.factory1.factory2": {
                    0: 1234567890,
                }
            },
            thread_safe=False,
        )
        assert (
            False
        ), "Should have raised ValueError for nested factory methods"
    except ValueError as e:
        error_msg = str(e)
        assert "nested factory methods are not supported" in error_msg
