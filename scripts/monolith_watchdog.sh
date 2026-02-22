#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK_PATH="${1:?watchdog lock path required}"
SUP_LOCK_PATH="${2:?supervisor lock path required}"
HEALTH_LOG="${3:?health log path required}"
shift 3

mkdir -p "$(dirname "$LOCK_PATH")" "$(dirname "$HEALTH_LOG")"
exec 9>"$LOCK_PATH"
if ! flock -n 9; then
  echo "watchdog already running: $LOCK_PATH" >&2
  exit 1
fi

echo "$$" 1>&9

RESTARTS=0
MAX_RESTARTS="${MAX_RESTARTS:-1000}"
BACKOFF_SEC="${BACKOFF_SEC:-30}"

while true; do
  TS="$(date -u +%Y%m%dT%H%M%SZ)"
  echo "[$TS] watchdog launching supervisor attempt=$((RESTARTS+1))" >> "$HEALTH_LOG"
  set +e
  "$ROOT/scripts/monolith_supervisor.sh" "$SUP_LOCK_PATH" "$@"
  RC=$?
  set -e
  TS2="$(date -u +%Y%m%dT%H%M%SZ)"
  echo "[$TS2] supervisor exited rc=$RC" >> "$HEALTH_LOG"

  if [[ $RC -eq 0 ]]; then
    echo "[$TS2] watchdog exiting success" >> "$HEALTH_LOG"
    exit 0
  fi

  RESTARTS=$((RESTARTS+1))
  if [[ $RESTARTS -ge $MAX_RESTARTS ]]; then
    echo "[$TS2] watchdog max restarts reached=$MAX_RESTARTS" >> "$HEALTH_LOG"
    exit 2
  fi

  sleep "$BACKOFF_SEC"
done
