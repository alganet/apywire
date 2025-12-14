#!/bin/bash

# SPDX-FileCopyrightText: 2025 Alexandre Gomes Gaigalas <alganet@gmail.com>
#
# SPDX-License-Identifier: ISC

# Demonstrates all three config formats

set -e

WORKDIR=$(mktemp -d)
trap "rm -rf $WORKDIR" EXIT
cd "$WORKDIR"

echo "=== JSON Format ==="
cat > config.json << 'EOF'
{
  "collections.OrderedDict settings": {
    "mapping": "{default_settings}"
  },
  "default_settings": {"debug": true, "timeout": 30}
}
EOF
echo "config.json:"
cat config.json
echo ""
echo "Compiled:"
python -m apywire compile --format json config.json

echo ""
echo "=== TOML Format ==="
cat > config.toml << 'EOF'
max_connections = 100
server_name = "localhost"

["collections.deque request_queue"]
maxlen = "{max_connections}"
EOF
echo "config.toml:"
cat config.toml
echo ""
echo "Compiled:"
python -m apywire compile --format toml config.toml

echo ""
echo "=== INI Format ==="
cat > config.ini << 'EOF'
[collections.Counter metrics]
iterable = {initial_counts}

[constants]
initial_counts = ["a", "b", "a", "c"]
EOF
echo "config.ini:"
cat config.ini
echo ""
echo "Compiled:"
python -m apywire compile --format ini config.ini
