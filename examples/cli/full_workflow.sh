#!/bin/bash

# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

# Full workflow: generate spec → customize → compile → run

set -e

WORKDIR=$(mktemp -d)
trap "rm -rf $WORKDIR" EXIT
cd "$WORKDIR"

echo "=== Step 1: Generate a spec file ==="
python -m apywire generate --format toml "datetime.datetime now" > app_config.toml
echo "Generated app_config.toml:"
cat app_config.toml

echo ""
echo "=== Step 2: Customize the spec ==="
# Override the generated defaults with actual values
cat > app_config.toml << 'EOF'
now_year = 2025
now_month = 6
now_day = 15
now_hour = 10
now_minute = 30
now_second = 0
now_microsecond = 0

["datetime.datetime now"]
year = "{now_year}"
month = "{now_month}"
day = "{now_day}"
hour = "{now_hour}"
minute = "{now_minute}"
second = "{now_second}"
microsecond = "{now_microsecond}"
EOF
echo "Customized app_config.toml:"
cat app_config.toml

echo ""
echo "=== Step 3: Compile to Python ==="
python -m apywire compile --format toml app_config.toml > app_wiring.py
echo "Generated app_wiring.py:"
cat app_wiring.py

echo ""
echo "=== Step 4: Run the compiled code ==="
python -c "
from app_wiring import compiled
dt = compiled.now()
print(f'Created datetime: {dt}')
print(f'Year: {dt.year}, Month: {dt.month}, Day: {dt.day}')
"

echo ""
echo "Done!"
