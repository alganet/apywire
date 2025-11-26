<!--
SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>

SPDX-License-Identifier: ISC
-->

# Basic App Example

This example demonstrates the core concepts of `apywire`:

1.  **Defining a Spec**: A dictionary that describes your application's components and their dependencies.
2.  **Wiring Objects**: Using the `Wiring` class to create a container.
3.  **Dependency Injection**: Automatically injecting dependencies (like `GreetingService` into `Greeter`).
4.  **Constants & Placeholders**: Using `{placeholder}` syntax to reference values and other objects.

## Running the Example

```bash
python app.py
```

Expected output:

```
Hello, World!
```
