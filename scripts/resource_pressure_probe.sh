#!/usr/bin/env bash
set -euo pipefail
RUN_DIR="${1:?run dir required}"
INTERVAL="${2:-15}"
OUT="$RUN_DIR/logs/forensics/resource_pressure.csv"
mkdir -p "$(dirname "$OUT")"

if [[ ! -f "$OUT" ]]; then
  echo "ts,mem_available_kb,mem_free_kb,swap_free_kb,swap_total_kb,psi_mem_some_avg10,psi_mem_full_avg10,psi_cpu_some_avg10,psi_io_some_avg10,gpu_util_pct,gpu_mem_used_mib,gpu_mem_total_mib,gpu_power_w,infer_pid,infer_rss_kb,infer_vms_kb,cgroup_memory_current,cgroup_memory_events" > "$OUT"
fi

while true; do
  ts="$(date -Is)"
  mem_avail=$(awk '/MemAvailable:/ {print $2}' /proc/meminfo 2>/dev/null || echo "")
  mem_free=$(awk '/MemFree:/ {print $2}' /proc/meminfo 2>/dev/null || echo "")
  swap_free=$(awk '/SwapFree:/ {print $2}' /proc/meminfo 2>/dev/null || echo "")
  swap_total=$(awk '/SwapTotal:/ {print $2}' /proc/meminfo 2>/dev/null || echo "")

  psi_mem_some=$(awk -F'avg10=' '/some/ {split($2,a," "); print a[1]}' /proc/pressure/memory 2>/dev/null || echo "")
  psi_mem_full=$(awk -F'avg10=' '/full/ {split($2,a," "); print a[1]}' /proc/pressure/memory 2>/dev/null || echo "")
  psi_cpu_some=$(awk -F'avg10=' '/some/ {split($2,a," "); print a[1]}' /proc/pressure/cpu 2>/dev/null || echo "")
  psi_io_some=$(awk -F'avg10=' '/some/ {split($2,a," "); print a[1]}' /proc/pressure/io 2>/dev/null || echo "")

  gpu_line=$(nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,power.draw --format=csv,noheader,nounits 2>/dev/null | head -n1 || true)
  gpu_util=$(echo "$gpu_line" | awk -F',' '{gsub(/ /,""); print $1}')
  gpu_mem_used=$(echo "$gpu_line" | awk -F',' '{gsub(/ /,""); print $2}')
  gpu_mem_total=$(echo "$gpu_line" | awk -F',' '{gsub(/ /,""); print $3}')
  gpu_power=$(echo "$gpu_line" | awk -F',' '{gsub(/ /,""); print $4}')

  infer_pid=$(ps -eo pid,cmd | grep 'runner/inference.py' | grep -v grep | head -n1 | awk '{print $1}' || true)
  infer_rss=""; infer_vms=""; cgroup_current=""; cgroup_events=""
  if [[ -n "${infer_pid:-}" ]]; then
    infer_rss=$(awk '/VmRSS:/ {print $2}' "/proc/$infer_pid/status" 2>/dev/null || echo "")
    infer_vms=$(awk '/VmSize:/ {print $2}' "/proc/$infer_pid/status" 2>/dev/null || echo "")
    cgp=$(awk -F: '/memory/ {print $3}' "/proc/$infer_pid/cgroup" 2>/dev/null | head -n1 || true)
    if [[ -n "${cgp:-}" ]]; then
      if [[ -f "/sys/fs/cgroup${cgp}/memory.current" ]]; then
        cgroup_current=$(cat "/sys/fs/cgroup${cgp}/memory.current" 2>/dev/null || echo "")
      fi
      if [[ -f "/sys/fs/cgroup${cgp}/memory.events" ]]; then
        cgroup_events=$(tr '\n' ';' < "/sys/fs/cgroup${cgp}/memory.events" 2>/dev/null || echo "")
      fi
    fi
  fi

  echo "$ts,$mem_avail,$mem_free,$swap_free,$swap_total,$psi_mem_some,$psi_mem_full,$psi_cpu_some,$psi_io_some,$gpu_util,$gpu_mem_used,$gpu_mem_total,$gpu_power,$infer_pid,$infer_rss,$infer_vms,$cgroup_current,\"$cgroup_events\"" >> "$OUT"

  if [[ -f "$RUN_DIR/run_status.json" ]]; then
    st=$(python3 - <<'PY' "$RUN_DIR/run_status.json"
import json,sys
try:
  print(json.load(open(sys.argv[1])).get('state',''))
except Exception:
  print('')
PY
)
    if [[ "$st" == "completed" || "$st" == "failed" || "$st" == "aborted" ]]; then
      exit 0
    fi
  fi

  sleep "$INTERVAL"
done
