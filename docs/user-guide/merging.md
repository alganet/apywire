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

The result is a plain [`Spec`](../api-reference.md#spec). Merging happens
*before* wiring, so `Wiring` and `WiringCompiler` consume the merged spec
exactly as they would a hand-written one — overlays add no wiring
semantics of their own.

Overlays fold left to right, so a base can be extended by plugins and
then by the user:

```python
spec = merge_specs(defaults, *plugin_specs, user_spec)
```

With no overlays at all, `merge_specs(base)` validates the base and
returns a copy. Inputs are never mutated, and the result shares no
mutable container with them, so you can merge the same defaults many
times over.

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
| wired entry | bare-name list | positional arguments replaced |
| wired entry | bare-name scalar | `MergeError` |
| entry key | same key | overlay's value replaces |
| entry key (a list) | `+key` | base's list, then the overlay's |

A **different type path replaces rather than merges**: the base's
arguments belong to the base's class, and passing them to a different
class would fail deep inside its constructor. The type path includes the
**factory method**, so `"pkg.C c.make"` and `"pkg.C c"` are different
entries — dropping `.make` from an overlay key replaces the entry rather
than extending it.

An overlay can only give a wired entry *arguments* — a dict (keyword) or
a list (positional). A scalar is a `MergeError` rather than a silent
demotion to a constant, which would drop the entry's class.

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

`+` is the **only** marker. It is meaningful at exactly the two levels
the merge operates on — a spec's keys, and a wired entry's arguments.
Deeper inside a value, or inside a constant (whose value is opaque data,
not a namespace), a `+` key is a `MergeError` rather than being passed
through to a constructor as a literal key.

### There is no way to remove or reorder

`+` only appends, and appends **last**. To drop an item from a base list,
or to put yours ahead of the base's, restate the whole list:

```toml
[registry]
repos = ["{repo_mdn}", "{repo_archive}"]   # mine first; wiktionary dropped
```

That re-couples your config to the base's list, which is what `+` exists
to avoid — so prefer `+` when order and removal don't matter to you.

## Errors

All of these raise `MergeError` (a `ValueError`):

| condition |
| --- |
| two keys in one spec expose the same name |
| a key starting with an unknown marker (`-key`, `^key`, …) |
| a `+` marker on a wired key (at spec level) |
| a `+` marker on a positional (integer) key (inside an entry) |
| a `+` marker below an entry's arguments, or inside a constant |
| a mapping holding both `key` and `+key` |
| `+key` where the base has no `key` to append to |
| `+key` where the base's value, or the overlay's, is not a list |
| a scalar given as a wired entry's arguments |

`MergeError` is deliberately **not** a `WiringError`: that one subclasses
`AttributeError`, so a failure raised through it could be swallowed by a
`hasattr` or `getattr` guard in calling code.

A **malformed spec key** (one with no module qualification, like
`"Database db"`) raises a plain `ValueError` from the shared key parser —
the same one `Wiring` would raise. Catch `ValueError` to cover both.

Merging validates the *merge*, not the wiring: cycles and unknown
placeholders are still raised by `Wiring(...)` itself when it receives
the merged spec. In one respect `merge_specs` is **stricter** than
`Wiring` — it rejects duplicate exposed names, which `Wiring` silently
resolves by keeping just one. A spec that wires today can therefore fail
to merge.

## Overlaying compiled defaults

A compiled container carries accessors, not data — so on its own it
cannot be overlaid. Compile with
[`--emit-spec`](compilation.md#emit_spec-emitting-the-source-spec) and it
also carries the spec it was built from:

```bash
python -m apywire compile --format toml --emit-spec defaults.toml > _defaults.py
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

## Seeing what a config merges to

`merge` prints the effective spec, so "why is my config being ignored?"
has an answer that doesn't need a REPL:

```bash
python -m apywire merge --format toml defaults.toml user.toml
```

The base can be an importable name as well as a file, which is how you
inspect an overlay against *compiled* defaults:

```bash
python -m apywire merge --format toml myapp._defaults:spec user.toml
```

## Next Steps

- **[Configuration Files](configuration-files.md)** - Loading specs from TOML, JSON or INI
- **[Compilation](compilation.md)** - Emitting the spec alongside a compiled container
- **[Basic Usage](basic-usage.md)** - What a merged spec becomes once wired
