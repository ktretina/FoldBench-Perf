#!/bin/bash
set -euo pipefail

af3_input_json=$1
input_dir=$2
prediction_dir=$3
evaluation_dir=$4
gpu_id=$5

PYTHON_PATH="/opt/conda/bin/python"

# Explicit model/checkpoint contract (required for reproducible benchmark claims)
MODEL_ID="${PROTENIX_MODEL_ID:-unknown_model}"
CHECKPOINT_PATH="${PROTENIX_CHECKPOINT_PATH:-}"
MODEL_NAME="${PROTENIX_MODEL_NAME:-}"
if [[ -z "$CHECKPOINT_PATH" ]]; then
  echo "ERROR: PROTENIX_CHECKPOINT_PATH is required and must point to the exact checkpoint file." >&2
  exit 2
fi
if [[ ! -f "$CHECKPOINT_PATH" ]]; then
  echo "ERROR: checkpoint not found: $CHECKPOINT_PATH" >&2
  exit 2
fi
if [[ -z "$MODEL_NAME" ]]; then
  case "$MODEL_ID" in
    Protenix-v1) MODEL_NAME="protenix_base_default_v1.0.0" ;;
    Protenix-v1-20250630) MODEL_NAME="protenix_base_20250630_v1.0.0" ;;
    *) MODEL_NAME="protenix_base_default_v1.0.0" ;;
  esac
fi

mkdir -p "$prediction_dir" "$evaluation_dir" "$input_dir"
CHECKPOINT_SHA256=$(sha256sum "$CHECKPOINT_PATH" | awk '{print $1}')
cat > "$prediction_dir/checkpoint_attestation.json" <<JSON
{
  "model_id": "$MODEL_ID",
  "checkpoint_path": "$CHECKPOINT_PATH",
  "checkpoint_sha256": "$CHECKPOINT_SHA256"
}
JSON

# convert af3 input data to model format
$PYTHON_PATH ./preprocess.py --af3_input_json="$af3_input_json" --input_dir="$input_dir"

# run inference
export CUDA_VISIBLE_DEVICES=$gpu_id
N_sample=5
N_step=200
N_cycle=10
seed="${PROTENIX_SEEDS:-42,66,101,2024,8888}"

if ! $PYTHON_PATH - <<'PY' >/dev/null 2>&1
import torch
raise SystemExit(0 if torch.cuda.is_available() else 1)
PY
then
  echo "ERROR: CUDA is not visible in container. True GPU path is required; aborting." >&2
  exit 3
fi

$PYTHON_PATH /algo/Protenix/runner/inference.py \
  --seeds ${seed} \
  --model_name "$MODEL_NAME" \
  --dump_dir ${prediction_dir} \
  --input_json_path "$input_dir/inputs.json" \
  --load_checkpoint_path "$CHECKPOINT_PATH" \
  --model.N_cycle ${N_cycle} \
  --sample_diffusion.N_sample ${N_sample} \
  --sample_diffusion.N_step ${N_step}

# Convert predictions to the general cif format,
# and generate evaluation prediction_reference.csv in evaluation_dir
$PYTHON_PATH ./postprocess.py --input_dir="$input_dir" --prediction_dir="$prediction_dir" --evaluation_dir="$evaluation_dir"