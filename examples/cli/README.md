<!--
SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>

SPDX-License-Identifier: ISC
-->

# CLI Examples

This folder demonstrates the full apywire CLI workflow: generating specs and compiling them to Python code.

## Full Workflow Example

```bash
# 1. Generate a spec file
python -m apywire generate --format toml "datetime.datetime now" > myapp.toml

# 2. Edit the spec to customize values
cat myapp.toml

# 3. Compile to Python code
python -m apywire compile --format toml myapp.toml > myapp_wiring.py

# 4. Use in your application
python -c "from myapp_wiring import compiled; print(compiled.now())"
```

## Scripts

- **full_workflow.sh** - Complete generate → edit → compile → run example
- **formats_demo.sh** - Shows all three config formats (JSON, TOML, INI)

## Running

```bash
chmod +x *.sh
./full_workflow.sh
```
