#!/usr/bin/env bash
set -euo pipefail
RUN_DIR="${1:?run dir required}"
TAG="${2:-manual}"
OUT="$RUN_DIR/logs/forensics/boundary_${TAG}_$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$OUT"

(ps -eo pid,ppid,etime,%cpu,%mem,rss,vsz,cmd | grep -E 'runner/inference.py|run_full_targets.sh|apptainer|python' | grep -v grep || true) > "$OUT/ps.txt"
nvidia-smi -q > "$OUT/nvidia_smi_q.txt" 2>&1 || true
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader,nounits > "$OUT/nvidia_apps.csv" 2>&1 || true
tail -n 300 "$RUN_DIR/logs/Protenix_time.log" > "$OUT/protenix_tail.txt" 2>&1 || true

pid=$(ps -eo pid,cmd | grep 'runner/inference.py' | grep -v grep | head -n1 | awk '{print $1}' || true)
if [[ -n "${pid:-}" ]]; then
  cat "/proc/$pid/status" > "$OUT/proc_${pid}_status.txt" 2>/dev/null || true
  cat "/proc/$pid/limits" > "$OUT/proc_${pid}_limits.txt" 2>/dev/null || true
  cat "/proc/$pid/smaps_rollup" > "$OUT/proc_${pid}_smaps_rollup.txt" 2>/dev/null || true
  ls -l "/proc/$pid/fd" > "$OUT/proc_${pid}_fds.txt" 2>/dev/null || true
fi

echo "$OUT"
