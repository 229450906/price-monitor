#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
CONFIG="$ROOT/product_monitor_config.json"
TASK_NAME="product-price-monitor"
INTERVAL_MINUTES=2

while [[ $# -gt 0 ]]; do
  case "$1" in
    --interval-minutes)
      INTERVAL_MINUTES="${2:?Missing value for --interval-minutes}"
      shift 2
      ;;
    --name)
      TASK_NAME="${2:?Missing value for --name}"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$UNIT_DIR"

SERVICE_FILE="$UNIT_DIR/$TASK_NAME.service"
TIMER_FILE="$UNIT_DIR/$TASK_NAME.timer"

q() {
  printf "%s" "$1" | sed "s/'/'\\\\''/g"
}

ROOT_Q="$(q "$ROOT")"
PYTHON_Q="$(q "$PYTHON_BIN")"
SCRIPT_Q="$(q "$ROOT/product_price_monitor.py")"
CONFIG_Q="$(q "$CONFIG")"

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Product Price Monitor

[Service]
Type=oneshot
EnvironmentFile=-%h/.config/product-price-monitor.env
ExecStart=/usr/bin/env bash -lc 'cd '\''$ROOT_Q'\'' && exec '\''$PYTHON_Q'\'' '\''$SCRIPT_Q'\'' --config '\''$CONFIG_Q'\'' --once'
EOF

cat > "$TIMER_FILE" <<EOF
[Unit]
Description=Run Product Price Monitor every $INTERVAL_MINUTES minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=${INTERVAL_MINUTES}min
AccuracySec=30s
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now "$TASK_NAME.timer"

echo "Installed user systemd timer: $TASK_NAME.timer"
