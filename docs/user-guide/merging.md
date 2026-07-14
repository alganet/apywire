<!--
SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>

SPDX-License-Identifier: ISC
-->
# Merging Specs

`merge_specs` overlays one spec on top of another. Use it when a library
ships defaults and an application extends them, or when a spec is
assembled from several files.

```python
from apywire import Wiring, merge_specs

defaults = {
    "delay": 3.0,
    "pkg.Registry registry": {"repos": ["{repo_a}"], "cache": "/tmp"},
}
user = {
    "delay": 0.5,
    "registry": {"+repos": ["{repo_b}"]},
}

wired = Wiring(merge_specs(defaults, user))
```

The result is a plain [`Spec`](../api-reference.md). Merging happens
*before* wiring, so `Wiring` and `WiringCompiler` consume the merged spec
exactly as they would a hand-written one — overlays add no wiring
semantics of their own.

Overlays fold left to right, so a base can be extended by plugins and
then by the user:

```python
spec = merge_specs(defaults, *plugin_specs, user_spec)
```

With no overlays at all, `merge_specs(base)` validates the base and
returns a fresh copy.

## Entries match on their exposed name

A spec key carries both a type path and a name (`"pkg.Registry registry"`
exposes `registry`). **Entries are matched by the name**, so an overlay
can replace an entry with a different class:

```python
merge_specs(
    {"pkg.Registry registry": {"cache": "/tmp"}},
    {"mine.Registry registry": {"cache": "/var"}},
)
# {'mine.Registry registry': {'cache': '/var'}}
```

!!! warning "Why not just `{**base, **overlay}`?"

    Those two keys are different *strings*, so a dict merge keeps
    **both** — and `Wiring`, which keys entries by exposed name, then
    silently drops one of them. `merge_specs` matches on the name, so
    the overlay's entry genuinely replaces the base's.

## What merges, and what replaces

The merge is exactly **two levels deep**: spec, then entry. Values inside
an entry are constructor arguments, not configuration namespaces, so they
are replaced wholesale rather than recursed into.

| base | overlay | result |
| --- | --- | --- |
| — | any entry | added, after the base's entries |
| any entry | — | kept, in the base's position |
| constant | constant | overlay's value replaces |
| wired entry | same type path | **deep merge**, key by key |
| wired entry | different type path | overlay's entry replaces it |
| wired entry | bare-name dict | **deep merge** (see below) |
| wired entry | bare-name scalar | replaced; becomes a constant |
| entry key | same key | overlay's value replaces |
| entry key (a list) | `+key` | base's list, then the overlay's |

A **different type path replaces rather than merges**: the base's
arguments belong to the base's class, and passing them to a different
class would fail deep inside its constructor.

### Extending an entry without repeating its class path

A bare-name key extends the wired entry of that name, so a config need
not repeat — and keep in sync with — the class path a library owns:

```toml
[registry]           # extends the base's "pkg.Registry registry"
cache = "/var"
```

## Appending to a list: the `+` marker

A key prefixed with `+` appends to the base's list value for that key,
instead of replacing it. In TOML, quote it:

```toml
["mypkg.MdnRepo repo_mdn"]
url_pattern = "developer\\.mozilla\\.org/(.+)"

[registry]
"+repos" = ["{repo_mdn}"]     # the base's repos, then this one
```

The marker is stripped during the merge and never reaches a container.
It works at the top level too (`"+items" = [3]` on a constant list), and
on specs parsed from any format — TOML, JSON or INI — since it is a
property of the spec, not of the file syntax.

## Errors

All of these raise `MergeError` (a `ValueError`):

| condition |
| --- |
| two keys in one spec expose the same name |
| a `+` marker on a wired key, or on a positional (integer) key |
| a mapping holding both `key` and `+key` |
| `+key` where the base has no `key` to append to |
| `+key` where the base's value is not a list |
| `+key` whose own value is not a list |

`MergeError` is deliberately **not** a `WiringError`: that one subclasses
`AttributeError`, so a failure raised through it could be swallowed by a
`hasattr` or `getattr` guard in calling code.

Merging validates the *merge*, not the wiring. Cycles, unknown
placeholders and name collisions are still reported by `Wiring` when it
receives the merged spec.

## Overlaying compiled defaults

A compiled container carries accessors, not data — so on its own it
cannot be overlaid. Compile with
[`--emit-spec`](compilation.md#emit_spec-emitting-the-source-spec) and it
also carries the spec it was built from:

```bash
apywire compile --format toml --emit-spec defaults.toml > _defaults.py
```

```python
from apywire import Wiring, merge_specs
from apywire.formats import toml_to_spec

from ._defaults import spec as defaults

def load(config_path):
    user = toml_to_spec(open(config_path).read())
    return Wiring(merge_specs(defaults, user))
```

Defaults stay compiled and fast for the common path; a user's config
extends them rather than restating them.
