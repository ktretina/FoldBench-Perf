# PROTOCOL.md — FoldBench Protenix Benchmark Protocol (Publication-Oriented)

## 1. Objective
Establish a reproducible, statistically rigorous protocol for evaluating Protenix on FoldBench and preparing cross-model Pareto analysis.

## 2. Analysis Sets
Two mandatory analysis sets:
1. **FULL_2023PLUS**: canonical `targets/*.csv`
2. **SUBSET_2024PLUS**: derived `targets_2024/*.csv` using release-date enrichment pipeline

### 2.1 Freeze rules
- Freeze each set into immutable manifests:
  - `analysis_sets/ANALYSIS_SET_FULL.json`
  - `analysis_sets/ANALYSIS_SET_2024.json`
- Include sha256 checksums for all target CSV files and row counts.
- Any unresolved IDs during 2024 derivation must be listed and excluded deterministically.

## 3. Model Matrix and Comparability Labels
Model metadata is sourced from `scripts/model_matrix.yaml`.

### Required benchmarked Protenix variants
1. **Protenix-v1 (benchmark/default)**
   - checkpoint: `protenix_base_default_v1.0.0`
   - training cutoff: `2021-09-30`
   - comparability: `strict_comparable`

2. **Protenix-v1-20250630 (applied)**
   - checkpoint: `protenix_base_20250630_v1.0.0`
   - training cutoff: `2025-06-30`
   - comparability: `reference_only`

### Reporting rule
- Do **not** mix strict and reference-only models into one ranking claim.
- Publish two views:
  - **Strict leaderboard** (`strict_comparable` only)
  - **Applied/reference leaderboard** (includes `reference_only`, clearly caveated)

## 4. Fairness Constraints (Model-Comparable)
See `fairness_matrix.yaml`.
Required controls:
- Same GPU host class and isolation policy
- Same precision mode policy
- Same seed policy and number of samples per target
- Same timeout/retry policy
- Same inclusion/exclusion and failure accounting
- Same timing boundaries (exclude setup, include inference wall-time)

## 5. Timing Definitions
- **Excluded setup time**: image build, model download, cache population.
- **Included model runtime**: per-target inference call latency.
- **Reported separately**: preprocess, postprocess, evaluation wall-times.

Primary speed metrics:
- p50/p90/p95 inference latency (successful targets)
- successful targets/hour
- failure-adjusted throughput

## 6. Quality Endpoints
Primary task metrics are those produced by FoldBench `task_score_summary.py` (per task).
For global model comparison, report:
- Per-task metrics table
- Completion rate per task
- Composite score (if used) with explicit weighting rationale

## 7. Failure Taxonomy and Denominators
Every target must be assigned one terminal status:
- success
- timeout
- oom
- runtime_error
- invalid_output
- missing_ground_truth

Report both:
- quality among successful predictions
- quality over all targets (with failures as failed attempts)

## 8. Statistical Plan
Minimum:
- 2 timed replicates per model variant
- bootstrap CIs for key quality metrics and latency quantiles
- Pareto frontier with uncertainty bands (bootstrap)

## 9. Leakage/Comparability Declaration
For each model run, include:
- model version and checkpoint provenance
- known/claimed training cutoff
- strict-comparable vs reference-only label

## 10. Reproducibility Bundle
Each run must emit:
- run manifest with commit SHAs and container digest(s)
- command transcript and logs
- telemetry JSONL
- summary tables
- analysis set checksums

## 11. Acceptance Gates for Publication Use
A run is publication-eligible only if:
- G1 analysis set frozen and checksummed
- G2 fairness matrix satisfied
- G3 completion/failure accounting complete
- G4 required telemetry present
- G5 full + 2024 summaries generated for each required model variant
- G6 uncertainty analysis produced
