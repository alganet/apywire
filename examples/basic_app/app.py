# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

from dataclasses import dataclass

from apywire import Wiring


@dataclass
class GreetingService:
    greeting: str

    def greet(self, name: str) -> str:
        return f"{self.greeting}, {name}!"


@dataclass
class Greeter:
    service: GreetingService
    default_name: str

    def run(self) -> None:
        print(self.service.greet(self.default_name))


def main():
    spec = {
        # Define constants
        "greeting_msg": "Hello",
        "default_person": "World",
        # Define wired objects
        "__main__.GreetingService my_service": {
            "greeting": "{greeting_msg}",
        },
        "__main__.Greeter my_greeter": {
            "service": "{my_service}",
            "default_name": "{default_person}",
        },
    }

    wiring = Wiring(spec)
    # Access the wired object
    greeter = wiring.my_greeter()
    greeter.run()


if __name__ == "__main__":
    main()
