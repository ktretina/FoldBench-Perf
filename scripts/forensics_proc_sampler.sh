#!/usr/bin/env bash
set -euo pipefail
RUN_DIR="${1:?run dir required}"
INTERVAL="${2:-20}"
OUT="$RUN_DIR/logs/forensics/proc_live.log"
mkdir -p "$(dirname "$OUT")"

while true; do
  {
    date -Is
    ps -eo pid,ppid,etime,%cpu,%mem,rss,vsz,cmd \
      | grep -E 'run_full_targets.sh|runner/inference.py|apptainer|python3 scripts/observability_watchdog.py|hardened_launch_run.sh' \
      | grep -v grep || true
    echo "---"
  } >> "$OUT"

  if [[ -f "$RUN_DIR/run_status.json" ]]; then
    state="$(python3 - <<'PY' "$RUN_DIR/run_status.json"
import json,sys
try:
  print(json.load(open(sys.argv[1])).get('state',''))
except Exception:
  print('')
PY
)"
    if [[ "$state" == "completed" || "$state" == "failed" ]]; then
      exit 0
    fi
  fi

  sleep "$INTERVAL"
done
