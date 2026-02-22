# RUNBOOK_PROTENIX_FULL.md

End-to-end publication-oriented runbook to benchmark **both required Protenix variants** on FoldBench:
- full `targets/` (FULL_2023PLUS)
- required `targets_2024/` (SUBSET_2024PLUS)

This runbook is governed by:
- `PROTOCOL.md`
- `fairness_matrix.yaml`
- `telemetry_schema_v1.json`
- `scripts/model_matrix.yaml`

---

## 0) Required model variants

1. **Protenix-v1**
   - checkpoint: `protenix_base_default_v1.0.0`
   - training cutoff: `2021-09-30`
   - comparability: `strict_comparable`

2. **Protenix-v1-20250630**
   - checkpoint: `protenix_base_20250630_v1.0.0`
   - training cutoff: `2025-06-30`
   - comparability: `reference_only`

Do not merge these into a single ranking claim.

---

## 1) Assumptions

- Linux host, NVIDIA GPU, apptainer available
- FoldBench root: `/home/ktretina/.openclaw/workspace/github_projects/FoldBench`
- Conda: `/home/ktretina/miniconda`
- Conda env: `foldbench`

---

## 2) Preflight and data freeze (required)

```bash
cd /home/ktretina/.openclaw/workspace/github_projects/FoldBench

# Preflight
python3 scripts/preflight_protenix_full.py

# targets_2024 is mandatory
if [ ! -d targets_2024 ]; then
  echo "ERROR: targets_2024 missing. Generate first: python3 scripts/derive_2024_subset.py"
  exit 1
fi

# Freeze analysis sets (checksums + row counts)
python3 scripts/freeze_analysis_sets.py
ls -la analysis_sets/ANALYSIS_SET_*.json
```

---

## 3) Verify evaluation env + OST

```bash
source /home/ktretina/miniconda/etc/profile.d/conda.sh
conda activate foldbench

cd /home/ktretina/.openclaw/workspace/github_projects/FoldBench
python -V
which ost
ost --help | head -n 20
```

If OST fails with `libtiff.so.5`:

```bash
ln -sf "$CONDA_PREFIX/lib/libtiff.so.6" "$CONDA_PREFIX/lib/libtiff.so.5"
ost --help | head -n 20
```

---

## 4) Build containers

```bash
cd /home/ktretina/.openclaw/workspace/github_projects/FoldBench
./build_apptainer_images.sh | tee logs/build_all_models.log
```

Record image artifacts:

```bash
find . -maxdepth 4 -type f -name '*.sif' | sort > logs/image_artifacts.txt
```

---

## 5) Fair timing policy (required)

For Pareto fairness, timing must follow strict boundaries.

### Exclude from timed metrics
- container build
- checkpoint download
- first-time cache population

### Include in timed metrics
- per-target inference wall time (success/fail both logged)

### Also report separately
- preprocess wall time
- postprocess wall time
- evaluation wall time

### Fixed controls for all model runs
```bash
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export PYTHONHASHSEED=0
```

Same hardware class, same seed policy, same sample count, same timeout/retry policy.

---

## 6) Run matrix execution loop (both models)

Use this exact loop skeleton. Replace `<SET_CHECKPOINT_ENV_FOR_MODEL>` with your local checkpoint-selection mechanism.

```bash
source /home/ktretina/miniconda/etc/profile.d/conda.sh
conda activate foldbench
cd /home/ktretina/.openclaw/workspace/github_projects/FoldBench

RUN_ID="protenix_matrix_$(date -u +%Y%m%dT%H%M%SZ)"
BASE_RUN_DIR="runs/${RUN_ID}"
mkdir -p "$BASE_RUN_DIR"

for MODEL_ID in Protenix-v1 Protenix-v1-20250630; do
  MODEL_RUN_DIR="$BASE_RUN_DIR/$MODEL_ID"
  mkdir -p "$MODEL_RUN_DIR"

  # 1) metadata + baseline
  git rev-parse HEAD > "$MODEL_RUN_DIR/foldbench_commit.txt"
  nvidia-smi > "$MODEL_RUN_DIR/nvidia_smi_baseline.txt"
  cp scripts/model_matrix.yaml "$MODEL_RUN_DIR/model_matrix.yaml"

  # 2) configure checkpoint for this model variant
  # <SET_CHECKPOINT_ENV_FOR_MODEL>

  # 3) warmup run (excluded from Pareto)
  ./run_full_targets.sh 2>&1 | tee "logs/${RUN_ID}_${MODEL_ID}_warmup.log"

  # 4) timed run on FULL_2023PLUS
  nvidia-smi --query-gpu=timestamp,name,utilization.gpu,memory.used,memory.total,power.draw --format=csv -l 5 > "logs/${RUN_ID}_${MODEL_ID}_gpu_watch_full.csv" &
  GPU_PID=$!
  START=$(date +%s)
  ./run_full_targets.sh 2>&1 | tee "logs/${RUN_ID}_${MODEL_ID}_timed_full.log"
  END=$(date +%s)
  kill "$GPU_PID" || true
  echo "{\"phase\":\"full_pipeline\",\"analysis_set\":\"FULL_2023PLUS\",\"duration_s\":$((END-START))}" > "$MODEL_RUN_DIR/phase_walltime_full.json"

  # 5) evaluate FULL_2023PLUS
  python evaluate.py \
    --targets_dir ./targets \
    --evaluation_dir ./outputs/evaluation \
    --algorithm_name Protenix \
    --ground_truth_dir ./ground_truths \
    --targets interface_protein_ligand interface_protein_protein interface_antibody_antigen interface_protein_peptide interface_protein_rna interface_protein_dna monomer_protein monomer_rna monomer_dna \
    | tee "logs/${RUN_ID}_${MODEL_ID}_evaluate_full.log"

  python task_score_summary.py \
    --evaluation_dir ./outputs/evaluation \
    --target_dir ./targets \
    --output_path "$MODEL_RUN_DIR/summary_table_full_2023plus.csv" \
    --algorithm_names Protenix \
    --targets interface_protein_ligand interface_protein_protein interface_antibody_antigen interface_protein_peptide interface_protein_rna interface_protein_dna monomer_protein monomer_rna monomer_dna \
    --metric_type rank | tee "logs/${RUN_ID}_${MODEL_ID}_summary_full.log"

  # 6) evaluate SUBSET_2024PLUS (required)
  python task_score_summary.py \
    --evaluation_dir ./outputs/evaluation \
    --target_dir ./targets_2024 \
    --output_path "$MODEL_RUN_DIR/summary_table_2024plus.csv" \
    --algorithm_names Protenix \
    --targets interface_protein_ligand interface_protein_protein interface_antibody_antigen interface_protein_peptide interface_protein_rna interface_protein_dna monomer_protein monomer_rna monomer_dna \
    --metric_type rank | tee "logs/${RUN_ID}_${MODEL_ID}_summary_2024.log"

  # 7) aggregate per-target telemetry if produced by inference wrapper
  if [ -f "$MODEL_RUN_DIR/protenix_timing.jsonl" ]; then
    python3 scripts/aggregate_timing_jsonl.py --jsonl "$MODEL_RUN_DIR/protenix_timing.jsonl" > "$MODEL_RUN_DIR/timing_summary.json"
  fi

  # 8) stamp comparability label and manifest
  python3 scripts/label_comparability.py --model-id "$MODEL_ID" --out "$MODEL_RUN_DIR/comparability.json"

  cat > "$MODEL_RUN_DIR/manifest.json" <<JSON
{
  "run_id": "${RUN_ID}",
  "model_id": "${MODEL_ID}",
  "targets_full": "./targets",
  "targets_2024": "./targets_2024",
  "summary_full": "summary_table_full_2023plus.csv",
  "summary_2024": "summary_table_2024plus.csv"
}
JSON

  # 9) artifact gate
  python3 scripts/check_pareto_artifacts.py --run-dir "$MODEL_RUN_DIR"
done
```

---

## 7) Replicates + uncertainty (required for publication)

Run at least **2 timed replicates** per model variant under identical fairness controls.

Then run template stats pipeline:

```bash
cd /home/ktretina/.openclaw/workspace/github_projects/FoldBench
python3 scripts/stats_report_template.py
```

Required final stats deliverables:
- bootstrap CI for key quality metrics
- bootstrap CI for p50/p90 latency
- Pareto points with uncertainty bands

---

## 8) Acceptance criteria (publication-grade)

For **each** model variant (`Protenix-v1`, `Protenix-v1-20250630`):

- preprocess/inference/postprocess completed without silent drops
- evaluation raw outputs exist
- `summary_table_full_2023plus.csv` exists
- `summary_table_2024plus.csv` exists
- telemetry present and schema-compliant (`telemetry_schema_v1.json`)
- artifact gate passes:
  - `python3 scripts/check_pareto_artifacts.py --run-dir <model_run_dir>`
- comparability label emitted (`strict_comparable` vs `reference_only`)

Global gates:
- analysis-set freeze files present and checksummed
- >=2 timed replicates per model
- CI/uncertainty analysis completed

---

## 9) Reporting rule

Publish two sections:
1. **Strict-comparable results** (Protenix-v1)
2. **Reference-only applied results** (Protenix-v1-20250630)

Do not merge these into one leaderboard without explicit caveat.
