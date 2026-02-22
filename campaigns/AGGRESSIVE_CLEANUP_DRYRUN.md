# FoldBench Aggressive Cleanup Dry-Run

No deletions executed. This is a candidate list only.

| Candidate | Bucket | Size |
|---|---|---:|
| `algorithms/Protenix/container.sandbox` | container_sandbox | 35.9 GiB |
| `runs/monolith_resilient_s002_seg001_Protenix-v1_targets_20260222T041006Z` | runs | 325.2 MiB |
| `runs/monolith_resilient_s001_seg003_Protenix-v1_targets_20260221T175549Z` | runs | 300.8 MiB |
| `runs/monolith_resilient_s001_seg004_Protenix-v1_targets_20260221T195521Z` | runs | 284.9 MiB |
| `runs/monolith_resilient_s002_seg005_Protenix-v1_targets_20260222T091037Z` | runs | 275.0 MiB |
| `runs/monolith_resilient_s003_seg001_Protenix-v1_targets_20260222T133753Z` | runs | 264.8 MiB |
| `runs/monolith_resilient_s001_seg005_Protenix-v1_targets_20260221T220703Z` | runs | 250.9 MiB |
| `runs/monolith_resilient_s001_seg001_Protenix-v1_targets_20260221T144355Z` | runs | 248.3 MiB |
| `runs/monolith_resilient_s001_seg002_Protenix-v1_targets_20260221T164323Z` | runs | 237.2 MiB |
| `runs/monolith_resilient_s002_seg004_Protenix-v1_targets_20260222T080335Z` | runs | 209.9 MiB |
| `runs/monolith_resilient_s003_seg002_Protenix-v1_targets_20260222T151617Z` | runs | 209.5 MiB |
| `runs/monolith_resilient_s002_seg002_Protenix-v1_targets_20260222T062854Z` | runs | 191.0 MiB |
| `runs/monolith_resilient_s002_seg003_Protenix-v1_targets_20260222T072308Z` | runs | 167.6 MiB |
| `runs/diag_boundary_t15_t29_seed42_Protenix-v1_targets_20260220T232233Z` | runs | 102.8 MiB |
| `runs/step4_protenix_v1_full_20260220T170835Z` | runs | 66.9 MiB |
| `runs/step4_strict_full_shard001_retry2_Protenix-v1_targets_20260220T212040Z` | runs | 66.0 MiB |
| `runs/step4_strict_full_shard001_retry1_Protenix-v1_targets_20260220T195342Z` | runs | 66.0 MiB |
| `runs/micro_pilot_shard_001_Protenix-v1_targets_20260221T002516Z` | runs | 65.9 MiB |
| `runs/step4_strict_full_shard001_Protenix-v1_targets_20260220T184830Z` | runs | 65.7 MiB |
| `runs/monolith_resilient_s002_seg001_Protenix-v1_targets_20260222T033042Z` | runs | 61.3 MiB |
| `runs/diag_boundary_t25_t29_seed42_Protenix-v1_targets_20260220T225626Z` | runs | 56.2 MiB |
| `runs/monolith_resilient_s001_seg001_Protenix-v1_targets_20260221T051320Z` | runs | 53.7 MiB |
| `runs/monolith_resilient_s001_seg001_Protenix-v1_targets_20260221T055625Z` | runs | 53.7 MiB |
| `runs/diag_boundary_t28_t29_seed42_Protenix-v1_targets_20260220T221805Z` | runs | 30.3 MiB |
| `runs/microbatch_shard001_job_0001_Protenix-v1_targets_20260221T035412Z` | runs | 22.7 MiB |
| `runs/diag_8g4p_single_target_Protenix-v1_targets_20260220T205238Z` | runs | 20.4 MiB |
| `runs/diag_boundary_t29_only_seed42_Protenix-v1_targets_20260220T220338Z` | runs | 20.4 MiB |
| `examples/outputs_smoke_gpu_v1` | outputs_smoke | 13.9 MiB |
| `runs/step3_wiring_smoke` | runs | 13.9 MiB |
| `examples/outputs_smoke_gpu_20250630` | outputs_smoke | 13.9 MiB |
| `runs/isolated_shard001_001_Protenix-v1_targets_20260221T010906Z` | runs | 13.4 MiB |
| `runs/isolated_shard001_003_Protenix-v1_targets_20260221T014944Z` | runs | 9.1 MiB |
| `runs/isolated_shard001_003_Protenix-v1_targets_20260221T030505Z` | runs | 9.1 MiB |
| `runs/isolated_shard001_002_Protenix-v1_targets_20260221T011734Z` | runs | 6.5 MiB |
| `runs/isolated_shard001_003_Protenix-v1_targets_20260221T012339Z` | runs | 5.4 MiB |
| `examples/outputs_smoke_20250630` | outputs_smoke | 2.8 MiB |
| `tmp_step2_full_raw_json` | tmp_dirs | 1.3 MiB |
| `runs/isolated_shard001_003_Protenix-v1_targets_20260221T022507Z` | runs | 406.5 KiB |
| `runs/isolated_shard001_003_Protenix-v1_targets_20260221T023233Z` | runs | 391.4 KiB |
| `runs/diag_boundary_t1_t29_seed42_Protenix-v1_targets_20260221T001500Z` | runs | 79.3 KiB |

## Bucket totals
- container_sandbox: 35.9 GiB
- runs: 3.7 GiB
- outputs_smoke: 30.5 MiB
- tmp_dirs: 1.4 MiB
- logs_dir: 1.6 KiB

## Suggested deletion order (if approved)
1. `outputs_smoke*` and other test/demo outputs
2. old `runs/*` not referenced by finalized shards
3. temporary `tmp*` directories
4. `container.sandbox` only if image can be rebuilt quickly
