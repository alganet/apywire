# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

from dataclasses import dataclass
from typing import Protocol

from yaml import safe_load

from apywire import Wiring


class RedisClient(Protocol):
    def set(self, name: str, value: str) -> bool: ...
    def get(self, name: str) -> str | None: ...


@dataclass
class KVApp:
    client: RedisClient

    def run(self) -> None:
        print("Setting 'foo' to 'bar'...")
        self.client.set("foo", "bar")

        val = self.client.get("foo")
        print(f"Got 'foo': {val}")


if __name__ == "__main__":
    # Load the spec
    with open("config.yaml", "r") as f:
        spec = safe_load(f)

    # Initialize wiring
    wiring = Wiring(spec)

    # Get the app
    app = wiring.app()
    app.run()
