#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODEL_ID=""; CHECKPOINT=""; AF3_INPUT_JSON=""; TARGETS_DIR=""; GROUND_TRUTH_DIR=""; GPU_ID="0"; RUN_PREFIX="step4"; SKIP_EVAL="${SKIP_EVAL:-1}"; EVAL_ENV_NAME="${EVAL_ENV_NAME:-foldbench}"; EVAL_PYTHON="${EVAL_PYTHON:-}"; PROTENIX_SEEDS="${PROTENIX_SEEDS:-42,66,101,2024,8888}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --model-id) MODEL_ID="$2"; shift 2 ;;
    --checkpoint) CHECKPOINT="$2"; shift 2 ;;
    --af3-input-json) AF3_INPUT_JSON="$2"; shift 2 ;;
    --targets-dir) TARGETS_DIR="$2"; shift 2 ;;
    --ground-truth-dir) GROUND_TRUTH_DIR="$2"; shift 2 ;;
    --gpu-id) GPU_ID="$2"; shift 2 ;;
    --run-prefix) RUN_PREFIX="$2"; shift 2 ;;
    --skip-eval) SKIP_EVAL=1; shift ;;
    --run-eval) SKIP_EVAL=0; shift ;;
    --eval-env-name) EVAL_ENV_NAME="$2"; shift 2 ;;
    --eval-python) EVAL_PYTHON="$2"; shift 2 ;;
    --protenix-seeds) PROTENIX_SEEDS="$2"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

for v in MODEL_ID CHECKPOINT AF3_INPUT_JSON TARGETS_DIR GROUND_TRUTH_DIR; do
  if [[ -z "${!v}" ]]; then echo "missing $v" >&2; exit 2; fi
done

TS="$(date -u +%Y%m%dT%H%M%SZ)"
SET_BASENAME="$(basename "$TARGETS_DIR")"
RUN_ID="${RUN_PREFIX}_${MODEL_ID}_${SET_BASENAME}_${TS}"
RUN_DIR="$ROOT/runs/$RUN_ID/$SET_BASENAME"
mkdir -p "$RUN_DIR/logs/forensics"

CHECKPOINT_SHA256="$(sha256sum "$CHECKPOINT" | awk '{print $1}')"
AF3_SHA256="$(sha256sum "$AF3_INPUT_JSON" | awk '{print $1}')"
GIT_SHA="$(git rev-parse HEAD)"
LAUNCHER_PID="$$"

cat > "$RUN_DIR/launch_manifest.json" <<JSON
{
  "run_id": "$RUN_ID",
  "created_at_utc": "$TS",
  "model_id": "$MODEL_ID",
  "checkpoint": "$CHECKPOINT",
  "checkpoint_sha256": "$CHECKPOINT_SHA256",
  "af3_input_json": "$AF3_INPUT_JSON",
  "af3_input_sha256": "$AF3_SHA256",
  "git_sha": "$GIT_SHA",
  "targets_dir": "$TARGETS_DIR",
  "ground_truth_dir": "$GROUND_TRUTH_DIR",
  "gpu_id": "$GPU_ID",
  "skip_eval": "$SKIP_EVAL",
  "eval_env_name": "$EVAL_ENV_NAME",
  "eval_python": "$EVAL_PYTHON",
  "protenix_seeds": "$PROTENIX_SEEDS",
  "launcher_pid": $LAUNCHER_PID
}
JSON

cat > "$RUN_DIR/run_status.json" <<JSON
{"state":"running","started_at_utc":"$TS","run_id":"$RUN_ID"}
JSON

cat > "$RUN_DIR/logs/process_ledger.json" <<JSON
{
  "launcher": {"pid": $LAUNCHER_PID, "started_at_utc": "$TS"},
  "sidecars": {},
  "run": {}
}
JSON

echo "RUN_ID=$RUN_ID"
echo "RUN_DIR=$RUN_DIR"

# sidecar: kernel/system event capture
nohup bash -lc "journalctl -kf -o short-iso | grep -Ei 'oom|out of memory|killed process|sigkill|nvrm|xid|segfault|containerd|shim'" \
  > "$RUN_DIR/logs/forensics/journal_live.log" 2>&1 &
JOURNAL_PID=$!

# sidecar: process sampler
nohup "$ROOT/scripts/forensics_proc_sampler.sh" "$RUN_DIR" 20 > "$RUN_DIR/logs/forensics/proc_sampler.nohup.log" 2>&1 &
PROC_SAMPLER_PID=$!

# sidecar: resource/memory pressure probe
nohup "$ROOT/scripts/resource_pressure_probe.sh" "$RUN_DIR" 15 > "$RUN_DIR/logs/forensics/resource_probe.nohup.log" 2>&1 &
RESOURCE_PROBE_PID=$!

# launch watchdog
nohup python3 "$ROOT/scripts/observability_watchdog.py" --run-dir "$RUN_DIR" --interval 20 --stall-seconds 900 > "$RUN_DIR/logs/watchdog.nohup.log" 2>&1 &
WATCHDOG_PID=$!

python3 - "$RUN_DIR" "$JOURNAL_PID" "$PROC_SAMPLER_PID" "$RESOURCE_PROBE_PID" "$WATCHDOG_PID" <<'PY'
import json,sys
from pathlib import Path
run=Path(sys.argv[1]); j=int(sys.argv[2]); p=int(sys.argv[3]); rp=int(sys.argv[4]); w=int(sys.argv[5])
ledger=run/'logs/process_ledger.json'
d=json.loads(ledger.read_text())
d['sidecars']={'journal_pid':j,'proc_sampler_pid':p,'resource_probe_pid':rp,'watchdog_pid':w}
ledger.write_text(json.dumps(d,indent=2))
PY

# launch benchmark run as child and wait for explicit code capture
set +e
(
  export PROTENIX_MODEL_ID="$MODEL_ID"
  export PROTENIX_CHECKPOINT_PATH="$CHECKPOINT"
  export AF3_INPUT_JSON="$AF3_INPUT_JSON"
  export TARGETS_DIR="$TARGETS_DIR"
  export GROUND_TRUTH_DIR="$GROUND_TRUTH_DIR"
  export OUTPUT_ROOT_DIR="$RUN_DIR/outputs"
  export TIME_LOG_ROOT_DIR="$RUN_DIR/logs"
  export GPU_ID="$GPU_ID"
  export SKIP_EVAL="$SKIP_EVAL"
  export EVAL_ENV_NAME="$EVAL_ENV_NAME"
  export EVAL_PYTHON="$EVAL_PYTHON"
  export PROTENIX_SEEDS="$PROTENIX_SEEDS"
  ./run_full_targets.sh
) > "$RUN_DIR/logs/run.log" 2>&1 &
RUN_PID=$!

echo "$RUN_PID" > "$RUN_DIR/logs/run.pid"
python3 - "$RUN_DIR" "$RUN_PID" <<'PY'
import json,sys
from pathlib import Path
run=Path(sys.argv[1]); pid=int(sys.argv[2])
ledger=run/'logs/process_ledger.json'
d=json.loads(ledger.read_text())
d['run']={'pid':pid}
ledger.write_text(json.dumps(d,indent=2))
PY

wait "$RUN_PID"
RC=$?
set -e

END_TS="$(date -u +%Y%m%dT%H%M%SZ)"
STATE="completed"
if [[ $RC -ne 0 ]]; then STATE="failed"; fi

SIGNAL=""
if [[ $RC -gt 128 ]]; then
  SIGNAL="$(kill -l $((RC-128)) 2>/dev/null || true)"
fi

cat > "$RUN_DIR/run_status.json" <<JSON
{"state":"$STATE","run_id":"$RUN_ID","started_at_utc":"$TS","ended_at_utc":"$END_TS","exit_code":$RC,"signal":"$SIGNAL","watchdog_pid":$WATCHDOG_PID,"journal_pid":$JOURNAL_PID,"proc_sampler_pid":$PROC_SAMPLER_PID,"resource_probe_pid":$RESOURCE_PROBE_PID,"run_pid":$RUN_PID}
JSON

python3 - "$RUN_DIR" "$RC" "$SIGNAL" <<'PY'
import json,sys
from datetime import datetime,timezone
from pathlib import Path
run=Path(sys.argv[1]); rc=int(sys.argv[2]); sig=sys.argv[3]
ledger=run/'logs/process_ledger.json'
d=json.loads(ledger.read_text())
d['run']['exit_code']=rc
d['run']['signal']=sig
d['run']['ended_at_utc']=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
ledger.write_text(json.dumps(d,indent=2))
PY

# stop sidecars now that run is terminal
kill "$JOURNAL_PID" "$PROC_SAMPLER_PID" "$RESOURCE_PROBE_PID" 2>/dev/null || true

# allow watchdog to observe final state and exit
sleep 2

echo "RUN_ID=$RUN_ID"
echo "RUN_DIR=$RUN_DIR"
echo "EXIT_CODE=$RC"
exit $RC
