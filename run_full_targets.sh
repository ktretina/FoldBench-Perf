#!/usr/bin/env bash
set -euo pipefail

# Full-target Protenix runner (single set, single model variant).
# This avoids examples-only defaults in run.sh and enforces true-GPU runtime.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

ALGORITHM_NAME="${ALGORITHM_NAME:-Protenix}"
GPU_ID="${GPU_ID:-0}"

AF3_INPUT_JSON="${AF3_INPUT_JSON:-$ROOT/inputs/full_2023plus/alphafold3_inputs.json}"
TARGETS_DIR="${TARGETS_DIR:-$ROOT/targets}"
GROUND_TRUTH_DIR="${GROUND_TRUTH_DIR:-$ROOT/data/foldbench_referenced_cifs/extracted/ground_truth_20250520}"
OUTPUT_ROOT_DIR="${OUTPUT_ROOT_DIR:-$ROOT/outputs}"
TIME_LOG_ROOT_DIR="${TIME_LOG_ROOT_DIR:-$ROOT/logs}"
SKIP_EVAL="${SKIP_EVAL:-1}"
EVAL_ENV_NAME="${EVAL_ENV_NAME:-foldbench}"
EVAL_PYTHON="${EVAL_PYTHON:-}"

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]

Options:
  --af3-input-json <path>
  --targets-dir <path>
  --ground-truth-dir <path>
  --output-root-dir <path>
  --time-log-root-dir <path>
  --algorithm-name <name>    (default: Protenix)
  --gpu-id <id>              (default: 0)
  --skip-eval                (only run preprocess/inference/postprocess)
  --run-eval                 (run evaluation stage after inference)
  --eval-python <exe>        (explicit python executable for evaluate.py)
  --eval-env-name <name>     (conda env name for eval when eval-python not provided; default: foldbench)
  -h, --help

Required env for reproducible runs:
  PROTENIX_MODEL_ID
  PROTENIX_CHECKPOINT_PATH
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --af3-input-json) AF3_INPUT_JSON="$2"; shift 2 ;;
    --targets-dir) TARGETS_DIR="$2"; shift 2 ;;
    --ground-truth-dir) GROUND_TRUTH_DIR="$2"; shift 2 ;;
    --output-root-dir) OUTPUT_ROOT_DIR="$2"; shift 2 ;;
    --time-log-root-dir) TIME_LOG_ROOT_DIR="$2"; shift 2 ;;
    --algorithm-name) ALGORITHM_NAME="$2"; shift 2 ;;
    --gpu-id) GPU_ID="$2"; shift 2 ;;
    --skip-eval) SKIP_EVAL=1; shift ;;
    --run-eval) SKIP_EVAL=0; shift ;;
    --eval-python) EVAL_PYTHON="$2"; shift 2 ;;
    --eval-env-name) EVAL_ENV_NAME="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ -z "${PROTENIX_MODEL_ID:-}" ]]; then
  echo "ERROR: PROTENIX_MODEL_ID is required" >&2
  exit 2
fi
if [[ -z "${PROTENIX_CHECKPOINT_PATH:-}" ]]; then
  echo "ERROR: PROTENIX_CHECKPOINT_PATH is required" >&2
  exit 2
fi
if [[ ! -f "$PROTENIX_CHECKPOINT_PATH" ]]; then
  echo "ERROR: checkpoint not found: $PROTENIX_CHECKPOINT_PATH" >&2
  exit 2
fi

for p in "$AF3_INPUT_JSON" "$TARGETS_DIR" "$GROUND_TRUTH_DIR"; do
  if [[ ! -e "$p" ]]; then
    echo "ERROR: required path missing: $p" >&2
    exit 2
  fi
done

PREDICTION_ROOT_DIR="$OUTPUT_ROOT_DIR/prediction"
EVALUATION_ROOT_DIR="$OUTPUT_ROOT_DIR/evaluation"
INPUT_ROOT_DIR="$OUTPUT_ROOT_DIR/input"

mkdir -p "$PREDICTION_ROOT_DIR" "$EVALUATION_ROOT_DIR" "$INPUT_ROOT_DIR" "$TIME_LOG_ROOT_DIR"

PREDICTION_DIR="$PREDICTION_ROOT_DIR/${ALGORITHM_NAME}"
INPUT_DIR="$INPUT_ROOT_DIR/${ALGORITHM_NAME}"
EVALUATION_DIR="$EVALUATION_ROOT_DIR/${ALGORITHM_NAME}"
TIME_LOG_FILE="$TIME_LOG_ROOT_DIR/${ALGORITHM_NAME}_time.log"

mkdir -p "$PREDICTION_DIR" "$INPUT_DIR" "$EVALUATION_DIR"

APPTAINER_BIN="${APPTAINER_BIN:-}"
if [[ -z "$APPTAINER_BIN" ]]; then
  if command -v apptainer >/dev/null 2>&1; then
    APPTAINER_BIN="$(command -v apptainer)"
  elif [[ -x "/home/ktretina/miniconda/bin/apptainer" ]]; then
    APPTAINER_BIN="/home/ktretina/miniconda/bin/apptainer"
  else
    echo "ERROR: apptainer not found (PATH or /home/ktretina/miniconda/bin/apptainer)." >&2
    exit 2
  fi
fi

GPU_CHECK_TARGET="$ROOT/algorithms/Protenix/container.sandbox"
if [[ ! -d "$GPU_CHECK_TARGET" ]]; then
  GPU_CHECK_TARGET="$ROOT/algorithms/Protenix/container.sif"
fi
if ! "$APPTAINER_BIN" exec --nvccli "$GPU_CHECK_TARGET" nvidia-smi -L >/dev/null 2>&1; then
  echo "ERROR: true GPU path check failed (apptainer --nvccli nvidia-smi -L). Aborting." >&2
  exit 3
fi

if [[ ! -f "$ROOT/algorithms/${ALGORITHM_NAME}/container.sif" ]]; then
  echo "ERROR: missing container image: $ROOT/algorithms/${ALGORITHM_NAME}/container.sif" >&2
  exit 2
fi

# If evaluation is requested, fail fast on eval runtime/dependency issues before expensive inference.
EVAL_CMD=()
if [[ "$SKIP_EVAL" != "1" ]]; then
  if [[ -n "$EVAL_PYTHON" ]]; then
    EVAL_CMD=("$EVAL_PYTHON")
  elif [[ -x "/home/ktretina/miniconda/bin/conda" ]]; then
    EVAL_CMD=("/home/ktretina/miniconda/bin/conda" run -n "$EVAL_ENV_NAME" python3)
  elif command -v conda >/dev/null 2>&1; then
    EVAL_CMD=(conda run -n "$EVAL_ENV_NAME" python3)
  else
    echo "ERROR: --run-eval requested but no evaluation python/conda runtime found." >&2
    echo "Set EVAL_PYTHON or install/point conda env '$EVAL_ENV_NAME'." >&2
    exit 4
  fi

  if ! "${EVAL_CMD[@]}" -c "import pandas, ost" >/dev/null 2>&1; then
    echo "ERROR: evaluation runtime missing required deps (pandas and/or ost)." >&2
    echo "Use --skip-eval for inference-only, or fix eval env before rerun." >&2
    exit 5
  fi
fi

echo "[run_full_targets] model=$PROTENIX_MODEL_ID input=$(basename "$AF3_INPUT_JSON") targets=$(basename "$TARGETS_DIR")"
echo "[run_full_targets] output_root=$OUTPUT_ROOT_DIR"

# Ensure critical run contract env vars are explicitly injected into the container runtime.
export APPTAINERENV_PROTENIX_MODEL_ID="${PROTENIX_MODEL_ID}"
export APPTAINERENV_PROTENIX_CHECKPOINT_PATH="${PROTENIX_CHECKPOINT_PATH}"
export APPTAINERENV_PROTENIX_SEEDS="${PROTENIX_SEEDS:-42,66,101,2024,8888}"

{ time (
  "$APPTAINER_BIN" exec --userns --nvccli \
    -B "$AF3_INPUT_JSON":/algo/alphafold3_inputs.json \
    -B "$OUTPUT_ROOT_DIR":/algo/outputs \
    "$ROOT/algorithms/${ALGORITHM_NAME}/container.sif" \
    bash -lc "cd /algo && ./make_predictions.sh /algo/alphafold3_inputs.json /algo/outputs/input/${ALGORITHM_NAME} /algo/outputs/prediction/${ALGORITHM_NAME} /algo/outputs/evaluation/${ALGORITHM_NAME} ${GPU_ID}"
) ; } 2>"$TIME_LOG_FILE"

if [[ "$SKIP_EVAL" == "1" ]]; then
  echo "[run_full_targets] SKIP_EVAL=1; inference completed."
  exit 0
fi

"${EVAL_CMD[@]}" "$ROOT/evaluate.py" \
  --targets_dir "$TARGETS_DIR" \
  --evaluation_dir "$EVALUATION_ROOT_DIR" \
  --algorithm_name "$ALGORITHM_NAME" \
  --ground_truth_dir "$GROUND_TRUTH_DIR" \
  --targets interface_protein_ligand interface_protein_protein interface_antibody_antigen interface_protein_peptide interface_protein_rna interface_protein_dna monomer_protein monomer_rna monomer_dna

echo "[run_full_targets] completed eval for $ALGORITHM_NAME using ${EVAL_CMD[*]}"
