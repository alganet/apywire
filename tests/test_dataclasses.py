# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

from dataclasses import InitVar, dataclass, field
from typing import Protocol

import apywire


@dataclass
class Config:
    host: str
    port: int


@dataclass
class App:
    config: Config
    name: str


@dataclass
class DefaultConfig:
    host: str = "localhost"
    port: int = 8080


@dataclass
class PostInitConfig:
    host: str
    port: int
    url: str = field(init=False)

    def __post_init__(self) -> None:
        self.url = f"http://{self.host}:{self.port}"


@dataclass
class InitVarConfig:
    host: str
    port: int
    debug: InitVar[bool] = False
    mode: str = field(init=False)

    def __post_init__(self, debug: bool) -> None:
        self.mode = "debug" if debug else "production"


def test_dataclass_runtime() -> None:
    spec: apywire.Spec = {
        "tests.test_dataclasses.Config config": {
            "host": "localhost",
            "port": 8080,
        }
    }
    wired = apywire.Wiring(spec)
    config = wired.config()
    assert isinstance(config, Config)
    assert config.host == "localhost"
    assert config.port == 8080


def test_dataclass_compiled() -> None:
    spec: apywire.Spec = {
        "tests.test_dataclasses.Config config": {
            "host": "localhost",
            "port": 8080,
        }
    }
    compiler = apywire.WiringCompiler(spec)
    code = compiler.compile()

    class MockConfig(Protocol):
        def config(self) -> Config: ...

    execd: dict[str, MockConfig] = {}
    exec(code, execd)

    wired = execd["compiled"]
    config = wired.config()

    assert isinstance(config, Config)
    assert config.host == "localhost"
    assert config.port == 8080


def test_nested_dataclass_runtime() -> None:
    spec: apywire.Spec = {
        "tests.test_dataclasses.Config config": {
            "host": "localhost",
            "port": 8080,
        },
        "tests.test_dataclasses.App app": {
            "config": "{config}",
            "name": "MyApp",
        },
    }
    wired = apywire.Wiring(spec)
    app = wired.app()
    assert isinstance(app, App)
    assert isinstance(app.config, Config)
    assert app.config.host == "localhost"
    assert app.name == "MyApp"


def test_nested_dataclass_compiled() -> None:
    spec: apywire.Spec = {
        "tests.test_dataclasses.Config config": {
            "host": "localhost",
            "port": 8080,
        },
        "tests.test_dataclasses.App app": {
            "config": "{config}",
            "name": "MyApp",
        },
    }
    compiler = apywire.WiringCompiler(spec)
    code = compiler.compile()

    class MockApp(Protocol):
        def app(self) -> App: ...

    execd: dict[str, MockApp] = {}
    exec(code, execd)

    wired = execd["compiled"]
    app = wired.app()

    assert isinstance(app, App)
    assert isinstance(app.config, Config)
    assert app.config.host == "localhost"
    assert app.name == "MyApp"


def test_dataclass_default_runtime() -> None:
    spec: apywire.Spec = {"tests.test_dataclasses.DefaultConfig config": {}}
    wired = apywire.Wiring(spec)
    config = wired.config()
    assert isinstance(config, DefaultConfig)
    assert config.host == "localhost"
    assert config.port == 8080


def test_dataclass_default_compiled() -> None:
    spec: apywire.Spec = {"tests.test_dataclasses.DefaultConfig config": {}}
    compiler = apywire.WiringCompiler(spec)
    code = compiler.compile()

    class MockDefaultConfig(Protocol):
        def config(self) -> DefaultConfig: ...

    execd: dict[str, MockDefaultConfig] = {}
    exec(code, execd)

    wired = execd["compiled"]
    config = wired.config()

    assert isinstance(config, DefaultConfig)
    assert config.host == "localhost"
    assert config.port == 8080


def test_dataclass_post_init_runtime() -> None:
    spec: apywire.Spec = {
        "tests.test_dataclasses.PostInitConfig config": {
            "host": "localhost",
            "port": 8080,
        }
    }
    wired = apywire.Wiring(spec)
    config = wired.config()
    assert isinstance(config, PostInitConfig)
    assert config.host == "localhost"
    assert config.port == 8080
    assert config.url == "http://localhost:8080"


def test_dataclass_post_init_compiled() -> None:
    spec: apywire.Spec = {
        "tests.test_dataclasses.PostInitConfig config": {
            "host": "localhost",
            "port": 8080,
        }
    }
    compiler = apywire.WiringCompiler(spec)
    code = compiler.compile()

    class MockPostInitConfig(Protocol):
        def config(self) -> PostInitConfig: ...

    execd: dict[str, MockPostInitConfig] = {}
    exec(code, execd)

    wired = execd["compiled"]
    config = wired.config()

    assert isinstance(config, PostInitConfig)
    assert config.host == "localhost"
    assert config.port == 8080
    assert config.url == "http://localhost:8080"


def test_dataclass_init_var_runtime() -> None:
    spec: apywire.Spec = {
        "tests.test_dataclasses.InitVarConfig config": {
            "host": "localhost",
            "port": 8080,
            "debug": True,
        }
    }
    wired = apywire.Wiring(spec)
    config = wired.config()
    assert isinstance(config, InitVarConfig)
    assert config.host == "localhost"
    assert config.port == 8080
    assert config.mode == "debug"


def test_dataclass_init_var_compiled() -> None:
    spec: apywire.Spec = {
        "tests.test_dataclasses.InitVarConfig config": {
            "host": "localhost",
            "port": 8080,
            "debug": True,
        }
    }
    compiler = apywire.WiringCompiler(spec)
    code = compiler.compile()

    class MockInitVarConfig(Protocol):
        def config(self) -> InitVarConfig: ...

    execd: dict[str, MockInitVarConfig] = {}
    exec(code, execd)

    wired = execd["compiled"]
    config = wired.config()

    assert isinstance(config, InitVarConfig)
    assert config.host == "localhost"
    assert config.port == 8080
    assert config.mode == "debug"
