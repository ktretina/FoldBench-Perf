#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

RUN_DIR=""
ALGORITHM_NAME="Protenix"
TARGETS_DIR=""
GROUND_TRUTH_DIR=""
EVAL_ENV_NAME="${EVAL_ENV_NAME:-foldbench}"
EVAL_PYTHON="${EVAL_PYTHON:-}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-dir) RUN_DIR="$2"; shift 2 ;;
    --algorithm-name) ALGORITHM_NAME="$2"; shift 2 ;;
    --targets-dir) TARGETS_DIR="$2"; shift 2 ;;
    --ground-truth-dir) GROUND_TRUTH_DIR="$2"; shift 2 ;;
    --eval-env-name) EVAL_ENV_NAME="$2"; shift 2 ;;
    --eval-python) EVAL_PYTHON="$2"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$RUN_DIR" ]]; then
  echo "missing --run-dir" >&2
  exit 2
fi
if [[ -z "$TARGETS_DIR" ]]; then
  echo "missing --targets-dir" >&2
  exit 2
fi
if [[ -z "$GROUND_TRUTH_DIR" ]]; then
  echo "missing --ground-truth-dir" >&2
  exit 2
fi

if [[ -n "$EVAL_PYTHON" ]]; then
  EVAL_CMD=("$EVAL_PYTHON")
elif [[ -x "/home/ktretina/miniconda/bin/conda" ]]; then
  EVAL_CMD=("/home/ktretina/miniconda/bin/conda" run -n "$EVAL_ENV_NAME" python3)
elif command -v conda >/dev/null 2>&1; then
  EVAL_CMD=(conda run -n "$EVAL_ENV_NAME" python3)
else
  echo "ERROR: no evaluation runtime found" >&2
  exit 4
fi

"${EVAL_CMD[@]}" -c "import pandas, ost" >/dev/null 2>&1 || {
  echo "ERROR: evaluation runtime missing pandas/ost" >&2
  exit 5
}

OUT_JSON="$RUN_DIR/eval_status.json"
EVAL_DIR="$RUN_DIR/outputs/evaluation"
mkdir -p "$EVAL_DIR"

set +e
"${EVAL_CMD[@]}" "$ROOT/evaluate.py" \
  --targets_dir "$TARGETS_DIR" \
  --evaluation_dir "$EVAL_DIR" \
  --algorithm_name "$ALGORITHM_NAME" \
  --ground_truth_dir "$GROUND_TRUTH_DIR" \
  --targets interface_protein_ligand interface_protein_protein interface_antibody_antigen interface_protein_peptide interface_protein_rna interface_protein_dna monomer_protein monomer_rna monomer_dna
RC=$?
set -e

python3 - <<PY
import json,datetime
out={
  'state':'completed' if $RC==0 else 'failed',
  'exit_code':$RC,
  'evaluated_at_utc':datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ'),
  'eval_cmd':"""${EVAL_CMD[*]}"""
}
open('$OUT_JSON','w').write(json.dumps(out,indent=2))
print(json.dumps(out,indent=2))
PY

exit $RC
