#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK_PATH="${1:?lock path required}"
shift

mkdir -p "$(dirname "$LOCK_PATH")"
exec 9>"$LOCK_PATH"
if ! flock -n 9; then
  echo "another monolith supervisor already running: $LOCK_PATH" >&2
  exit 1
fi

echo "$$" 1>&9

RESTARTS=0
MAX_RESTARTS="${MAX_RESTARTS:-1000}"
BACKOFF_SEC="${BACKOFF_SEC:-20}"
HEALTH_LOG="${HEALTH_LOG:-$ROOT/runs/monolith_supervisor_health.log}"

while true; do
  TS="$(date -u +%Y%m%dT%H%M%SZ)"
  echo "[$TS] supervisor start attempt=$((RESTARTS+1)) cmd=$*" >> "$HEALTH_LOG"
  set +e
  "$@"
  RC=$?
  set -e
  TS2="$(date -u +%Y%m%dT%H%M%SZ)"
  echo "[$TS2] worker exit rc=$RC" >> "$HEALTH_LOG"

  if [[ $RC -eq 0 ]]; then
    echo "[$TS2] completed successfully" >> "$HEALTH_LOG"
    exit 0
  fi

  RESTARTS=$((RESTARTS+1))
  if [[ $RESTARTS -ge $MAX_RESTARTS ]]; then
    echo "[$TS2] max restarts reached=$MAX_RESTARTS" >> "$HEALTH_LOG"
    exit 2
  fi

  sleep "$BACKOFF_SEC"
done
