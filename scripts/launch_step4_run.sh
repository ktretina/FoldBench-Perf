#!/usr/bin/env bash
set -euo pipefail

# Deterministic launcher for long full-run jobs with explicit audit artifacts.
# Usage:
#   scripts/launch_step4_run.sh \
#     --model-id Protenix-v1 \
#     --checkpoint /abs/path/to/checkpoint.pt \
#     --af3-input-json /abs/path/to/alphafold3_inputs.json \
#     --targets-dir /abs/path/to/targets \
#     --ground-truth-dir /abs/path/to/ground_truth_20250520 \
#     [--gpu-id 0] [--run-prefix step4]

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODEL_ID=""
CHECKPOINT=""
AF3_INPUT_JSON=""
TARGETS_DIR=""
GROUND_TRUTH_DIR=""
GPU_ID="0"
RUN_PREFIX="step4"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --model-id) MODEL_ID="$2"; shift 2 ;;
    --checkpoint) CHECKPOINT="$2"; shift 2 ;;
    --af3-input-json) AF3_INPUT_JSON="$2"; shift 2 ;;
    --targets-dir) TARGETS_DIR="$2"; shift 2 ;;
    --ground-truth-dir) GROUND_TRUTH_DIR="$2"; shift 2 ;;
    --gpu-id) GPU_ID="$2"; shift 2 ;;
    --run-prefix) RUN_PREFIX="$2"; shift 2 ;;
    -h|--help)
      sed -n '1,35p' "$0"
      exit 0
      ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

for v in MODEL_ID CHECKPOINT AF3_INPUT_JSON TARGETS_DIR GROUND_TRUTH_DIR; do
  if [[ -z "${!v}" ]]; then
    echo "ERROR: missing required arg for $v" >&2
    exit 2
  fi
done

for p in "$CHECKPOINT" "$AF3_INPUT_JSON" "$TARGETS_DIR" "$GROUND_TRUTH_DIR"; do
  if [[ ! -e "$p" ]]; then
    echo "ERROR: path does not exist: $p" >&2
    exit 2
  fi
done

TS="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_ID="${RUN_PREFIX}_${MODEL_ID}_$(basename "$TARGETS_DIR")_${TS}"
RUN_DIR="$ROOT/runs/$RUN_ID"
SET_DIR="$RUN_DIR/$(basename "$TARGETS_DIR")"
mkdir -p "$SET_DIR"

CHECKPOINT_SHA256="$(sha256sum "$CHECKPOINT" | awk '{print $1}')"
LAUNCH_MANIFEST="$RUN_DIR/launch_manifest.json"
cat > "$LAUNCH_MANIFEST" <<JSON
{
  "run_id": "$RUN_ID",
  "created_at_utc": "$TS",
  "model_id": "$MODEL_ID",
  "checkpoint": "$CHECKPOINT",
  "checkpoint_sha256": "$CHECKPOINT_SHA256",
  "af3_input_json": "$AF3_INPUT_JSON",
  "targets_dir": "$TARGETS_DIR",
  "ground_truth_dir": "$GROUND_TRUTH_DIR",
  "gpu_id": "$GPU_ID",
  "set_dir": "$SET_DIR",
  "output_root_dir": "$SET_DIR/outputs",
  "time_log_root_dir": "$SET_DIR/logs",
  "launcher": "scripts/launch_step4_run.sh"
}
JSON

LOG_PATH="$SET_DIR/run.log"
PID_PATH="$RUN_DIR/runner.pid"

nohup env \
  PROTENIX_MODEL_ID="$MODEL_ID" \
  PROTENIX_CHECKPOINT_PATH="$CHECKPOINT" \
  AF3_INPUT_JSON="$AF3_INPUT_JSON" \
  TARGETS_DIR="$TARGETS_DIR" \
  GROUND_TRUTH_DIR="$GROUND_TRUTH_DIR" \
  OUTPUT_ROOT_DIR="$SET_DIR/outputs" \
  TIME_LOG_ROOT_DIR="$SET_DIR/logs" \
  GPU_ID="$GPU_ID" \
  "$ROOT/run_full_targets.sh" \
  > "$LOG_PATH" 2>&1 &

PID=$!
echo "$PID" > "$PID_PATH"

# Immediate verification
sleep 1
if ! ps -p "$PID" > /dev/null 2>&1; then
  echo "ERROR: launch failed; process exited immediately (pid=$PID)" >&2
  exit 1
fi

cat <<EOF
LAUNCHED
run_id=$RUN_ID
pid=$PID
run_dir=$RUN_DIR
set_dir=$SET_DIR
log=$LOG_PATH
manifest=$LAUNCH_MANIFEST
EOF
