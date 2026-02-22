#!/usr/bin/env bash
set -euo pipefail

RUN_DIR="$1"
while true; do
  python3 scripts/telemetry_build_dataset.py --run-dir "$RUN_DIR" --out "$RUN_DIR/logs/telemetry_dataset.json"
  python3 scripts/telemetry_render_graphs.py --dataset "$RUN_DIR/logs/telemetry_dataset.json" --out-dir "$RUN_DIR/logs/graphs"
  python3 scripts/telemetry_publish_update.py --run-dir "$RUN_DIR" --out-md "$RUN_DIR/logs/telemetry_update.md"
  sleep 1800
done
