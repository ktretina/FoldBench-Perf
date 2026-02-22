# FoldBench Current Implementation

## Runtime topology
- `scripts/run_monolith_segmented.py` orchestrates segmented execution and state.
- `scripts/monolith_supervisor.sh` wraps launcher for retry/resume continuity.
- `scripts/monolith_watchdog.sh` monitors/restarts the supervisor chain.
- `scripts/auto_continue_shards.sh` finalizes completed shards and launches next incomplete shard.
- Cron-driven automation previously ran every 10m for auto-continue and every 30m telemetry checkpoints.

## Data/metrics outputs
- `campaigns/pareto_dataset/*` (shard JSON, index, CSV, dashboard)
- `campaigns/strict_full_shard*_monolith_resilient/results_tables/*`
- Run-level telemetry in `runs/.../targets/logs/telemetry_dataset.json` + 8 SVG graphs

## Shard status snapshot
| Shard | Status | Done | Total | Segments |
|---|---:|---:|---:|---:|
| shard_001 | complete | 100 | 100 | 5 |
| shard_002 | complete | 100 | 100 | 5 |
| shard_003 | in_progress | 20 | 100 | 1 |
| shard_004 | not_started | 0 | 0 | 0 |
| shard_005 | not_started | 0 | 0 | 0 |
| shard_006 | not_started | 0 | 0 | 0 |
| shard_007 | not_started | 0 | 0 | 0 |
| shard_008 | not_started | 0 | 0 | 0 |
| shard_009 | not_started | 0 | 0 | 0 |
| shard_010 | not_started | 0 | 0 | 0 |
| shard_011 | not_started | 0 | 0 | 0 |
| shard_012 | not_started | 0 | 0 | 0 |
| shard_013 | not_started | 0 | 0 | 0 |
| shard_014 | not_started | 0 | 0 | 0 |
| shard_015 | not_started | 0 | 0 | 0 |
| shard_016 | not_started | 0 | 0 | 0 |
