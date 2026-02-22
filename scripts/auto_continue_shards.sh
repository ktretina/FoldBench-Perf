#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/ktretina/.openclaw/workspace/github_projects/FoldBench"
PARETO_ROOT="$ROOT/campaigns/pareto_dataset"
SHARDS_DIR="$ROOT/inputs/full_2023plus_shards"
MODEL_ID="Protenix-v1"
CHECKPOINT="$ROOT/checkpoints/protenix_base_default_v1.0.0.pt"
TARGETS_DIR="$ROOT/targets"
GT_DIR="$ROOT/data/foldbench_referenced_cifs/extracted/ground_truth_20250520"
SEEDS="42,66,101,2024,8888"
SAMPLES_PER_TARGET=5
SEGMENT_SIZE=20

active_any() {
  ps -eo cmd | grep -E '[m]onolith_watchdog.sh .*strict_full_shard[0-9]{3}_monolith_resilient|[r]un_monolith_segmented.py --af3-input-json .*/alphafold3_inputs_shard_[0-9]{3}\.json|[h]ardened_launch_run.sh --model-id Protenix-v1 .*monolith_resilient_s[0-9]{3}|/algo/Protenix/runner/inference.py' >/dev/null
}

active_shard_id() {
  ps -eo cmd | sed -nE 's#.*alphafold3_inputs_(shard_[0-9]{3})\.json.*#\1#p' | head -n1
}

kill_shard_chain() {
  local sid="$1"
  local sidc="${sid/_/}"
  local n="${sid#shard_}"
  pkill -f "strict_full_${sidc}_monolith_resilient/watchdog.lock" 2>/dev/null || true
  pkill -f "strict_full_${sidc}_monolith_resilient/supervisor.lock" 2>/dev/null || true
  pkill -f "alphafold3_inputs_${sid}\.json" 2>/dev/null || true
  pkill -f "monolith_resilient_s${n}" 2>/dev/null || true
}

shard_done() {
  local sid="$1"
  local sidc="${sid/_/}"
  local state="$ROOT/campaigns/strict_full_${sidc}_monolith_resilient/resume_state.json"
  python3 - <<'PY' "$state"
import json,sys,pathlib
p=pathlib.Path(sys.argv[1])
if not p.exists():
  print('0'); raise SystemExit(0)
j=json.load(open(p))
t=j.get('total_targets',0)
d=sum(1 for v in j.get('targets',{}).values() if v.get('ok'))
print('1' if t and d==t else '0')
PY
}

finalize_shard() {
  local sid="$1"
  local sidc="${sid/_/}"
  local run_tag="${sid/shard_/s}"
  local camp="$ROOT/campaigns/strict_full_${sidc}_monolith_resilient"
  mkdir -p "$camp"
  cat > "$camp/FINALIZED.md" <<EOF
# ${sid} FINALIZED

- Status: COMPLETE
- Model: ${MODEL_ID}
- Completion gate: PASS
- This shard is locked for analysis input.
EOF

  python3 "$ROOT/scripts/update_pareto_dataset.py" \
    --state-json "$camp/resume_state.json" \
    --aggregate-pred-root "$camp/aggregate/prediction/Protenix" \
    --af3-input-json "$SHARDS_DIR/alphafold3_inputs_${sid}.json" \
    --shard-id "$sid" \
    --model-id "$MODEL_ID" \
    --checkpoint "$CHECKPOINT" \
    --seeds "$SEEDS" \
    --samples-per-target "$SAMPLES_PER_TARGET" \
    --segment-size "$SEGMENT_SIZE" \
    --pareto-root "$PARETO_ROOT" \
    --variant-label "$MODEL_ID" \
    --quality-summary-csv "$camp/quality/${sid}_summary.csv" \
    --quality-primary-column DockQ \
    --quality-secondary-column rmsd >/dev/null || true

  python3 "$ROOT/scripts/update_run_results_tables.py" \
    --state-json "$camp/resume_state.json" \
    --pareto-root "$PARETO_ROOT" \
    --shard-id "$sid" \
    --model-id "$MODEL_ID" \
    --out-dir "$camp/results_tables" \
    --campaign-root "$PARETO_ROOT" >/dev/null || true
}

launch_shard() {
  local sid="$1"
  local sidc="${sid/_/}"
  local n="${sid#shard_}"
  local run_prefix="monolith_resilient_s${n}"
  local camp="$ROOT/campaigns/strict_full_${sidc}_monolith_resilient"
  mkdir -p "$camp/quality"

  nohup "$ROOT/scripts/monolith_watchdog.sh" \
    "$camp/watchdog.lock" "$camp/supervisor.lock" "$camp/watchdog_health.log" \
    python3 "$ROOT/scripts/run_monolith_segmented.py" \
      --af3-input-json "$SHARDS_DIR/alphafold3_inputs_${sid}.json" \
      --model-id "$MODEL_ID" \
      --checkpoint "$CHECKPOINT" \
      --targets-dir "$TARGETS_DIR" \
      --ground-truth-dir "$GT_DIR" \
      --gpu-id 0 \
      --seeds "$SEEDS" \
      --samples-per-target "$SAMPLES_PER_TARGET" \
      --segment-size "$SEGMENT_SIZE" \
      --run-prefix "$run_prefix" \
      --state-json "$camp/resume_state.json" \
      --work-dir "$camp" \
      --aggregate-pred-root "$camp/aggregate/prediction/Protenix" \
      --retries 1 \
      --shard-id "$sid" \
      --pareto-root "$PARETO_ROOT" \
      --variant-label "$MODEL_ID" \
      --quality-summary-csv "$camp/quality/${sid}_summary.csv" \
      --quality-primary-column DockQ \
      --quality-secondary-column rmsd \
    > "$camp/watchdog.nohup.log" 2>&1 &
}

# If a shard chain is active but already complete, stop stale chain and continue.
if active_any; then
  sid="$(active_shard_id || true)"
  if [[ -n "$sid" && "$(shard_done "$sid")" == "1" ]]; then
    kill_shard_chain "$sid"
    sleep 1
  else
    echo '{"action":"none","reason":"active_run_present"}'
    exit 0
  fi
fi

# finalize completed shards and find next incomplete
next=""
for f in "$SHARDS_DIR"/alphafold3_inputs_shard_*.json; do
  b="$(basename "$f")"
  sid="${b#alphafold3_inputs_}"; sid="${sid%.json}"
  if [[ "$(shard_done "$sid")" == "1" ]]; then
    finalize_shard "$sid"
    continue
  fi
  next="$sid"
  break
done

if [[ -z "$next" ]]; then
  # everything complete; refresh dashboard one last time
  python3 "$ROOT/scripts/update_campaign_dashboard.py" --campaign-root "$PARETO_ROOT" --pareto-root "$PARETO_ROOT" --total-shards 16 --default-shard-expected-samples 2500 >/dev/null || true
  echo '{"action":"none","reason":"all_shards_complete"}'
  exit 0
fi

launch_shard "$next"
echo "{\"action\":\"launch\",\"shard\":\"$next\"}"
