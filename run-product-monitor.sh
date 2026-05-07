#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
CONFIG="${CONFIG:-$ROOT/product_monitor_config.json}"

exec "$PYTHON_BIN" "$ROOT/product_price_monitor.py" --config "$CONFIG" "$@"
