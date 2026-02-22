#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/ktretina/.openclaw/workspace/github_projects/FoldBench"
CAMPAIGN_DIR="$ROOT/campaigns/strict_full_shard002_monolith_resilient"
STATE_FILE="$CAMPAIGN_DIR/watchdog_monitor_state.json"
WATCHDOG_LOCK="$CAMPAIGN_DIR/watchdog.lock"
SUP_LOCK="$CAMPAIGN_DIR/supervisor.lock"
HEALTH_LOG="$CAMPAIGN_DIR/watchdog_health.log"

mkdir -p "$CAMPAIGN_DIR"

latest_run_dir() {
  ls -dt "$ROOT"/runs/monolith_resilient_s002_seg*_Protenix-v1_targets_*/targets 2>/dev/null | head -n1 || true
}

sample_count() {
  local run_dir="$1"
  if [[ -z "$run_dir" ]]; then echo 0; return; fi
  find "$run_dir/outputs/prediction/Protenix" -type f -name '*_sample_*.cif' 2>/dev/null | wc -l
}

is_active() {
  if [[ ! -f "$WATCHDOG_LOCK" ]]; then
    return 1
  fi
  local pid
  pid=$(tr -dc '0-9' < "$WATCHDOG_LOCK" || true)
  if [[ -z "$pid" ]]; then
    return 1
  fi
  if ! kill -0 "$pid" 2>/dev/null; then
    return 1
  fi
  ps -p "$pid" -o cmd= | grep -q 'monolith_watchdog.sh'
}

kill_chain() {
  pkill -f 'monolith_watchdog.sh.*strict_full_shard002_monolith_resilient' 2>/dev/null || true
  pkill -f 'monolith_supervisor.sh.*strict_full_shard002_monolith_resilient' 2>/dev/null || true
  pkill -f 'run_monolith_segmented.py --af3-input-json .*/alphafold3_inputs_shard_002.json' 2>/dev/null || true
  pkill -f 'hardened_launch_run.sh --model-id Protenix-v1 .*monolith_resilient_s002' 2>/dev/null || true
}

start_watchdog() {
  cd "$ROOT"
  nohup scripts/monolith_watchdog.sh "$WATCHDOG_LOCK" "$SUP_LOCK" "$HEALTH_LOG" \
    python3 scripts/run_monolith_segmented.py \
      --af3-input-json /home/ktretina/.openclaw/workspace/github_projects/FoldBench/inputs/full_2023plus_shards/alphafold3_inputs_shard_002.json \
      --model-id Protenix-v1 \
      --checkpoint /home/ktretina/.openclaw/workspace/github_projects/FoldBench/checkpoints/protenix_base_default_v1.0.0.pt \
      --targets-dir /home/ktretina/.openclaw/workspace/github_projects/FoldBench/targets \
      --ground-truth-dir /home/ktretina/.openclaw/workspace/github_projects/FoldBench/data/foldbench_referenced_cifs/extracted/ground_truth_20250520 \
      --gpu-id 0 \
      --seeds 42,66,101,2024,8888 \
      --samples-per-target 5 \
      --segment-size 20 \
      --max-segments 1 \
      --run-prefix monolith_resilient_s002 \
      --state-json /home/ktretina/.openclaw/workspace/github_projects/FoldBench/campaigns/strict_full_shard002_monolith_resilient/resume_state.json \
      --work-dir /home/ktretina/.openclaw/workspace/github_projects/FoldBench/campaigns/strict_full_shard002_monolith_resilient \
      --aggregate-pred-root /home/ktretina/.openclaw/workspace/github_projects/FoldBench/campaigns/strict_full_shard002_monolith_resilient/aggregate/prediction/Protenix \
      --retries 1 \
      --shard-id shard_002 \
      --pareto-root /home/ktretina/.openclaw/workspace/github_projects/FoldBench/campaigns/pareto_dataset \
      --variant-label Protenix-v1 \
      --quality-summary-csv /home/ktretina/.openclaw/workspace/github_projects/FoldBench/campaigns/strict_full_shard002_monolith_resilient/quality/shard_002_summary.csv \
      --quality-primary-column DockQ \
      --quality-secondary-column rmsd \
    > "$CAMPAIGN_DIR/watchdog.nohup.log" 2>&1 &
}

now_epoch=$(date +%s)
run_dir=$(latest_run_dir)
sc=$(sample_count "$run_dir")

last_sc=0
last_change=$now_epoch
if [[ -f "$STATE_FILE" ]]; then
  last_sc=$(python3 - <<'PY' "$STATE_FILE"
import json,sys
try:
 d=json.load(open(sys.argv[1]))
 print(d.get('last_sample_count',0))
except Exception:
 print(0)
PY
)
  last_change=$(python3 - <<'PY' "$STATE_FILE" "$now_epoch"
import json,sys
try:
 d=json.load(open(sys.argv[1]))
 print(d.get('last_change_epoch',int(sys.argv[2])))
except Exception:
 print(int(sys.argv[2]))
PY
)
fi

if [[ "$sc" -gt "$last_sc" ]]; then
  last_change=$now_epoch
fi

active=0
if is_active; then active=1; fi

# Stall threshold: 20 minutes with no sample increase while chain appears active.
stalled=0
if [[ "$active" -eq 1 && $((now_epoch-last_change)) -ge 1200 ]]; then
  stalled=1
fi

action="none"
if [[ "$active" -eq 0 || "$stalled" -eq 1 ]]; then
  kill_chain
  sleep 1
  start_watchdog
  action="restart"
fi

python3 - <<'PY' "$STATE_FILE" "$sc" "$last_change" "$run_dir" "$action" "$now_epoch"
import json,sys
path,sc,last_change,run_dir,action,now = sys.argv[1:]
obj={
 'last_sample_count': int(sc),
 'last_change_epoch': int(last_change),
 'last_run_dir': run_dir,
 'last_action': action,
 'updated_epoch': int(now)
}
with open(path,'w') as f:
 json.dump(obj,f,indent=2)
print(json.dumps(obj))
PY
