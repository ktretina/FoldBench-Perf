# FoldBench Tier-2 Dry-Run (Monolith Runs)

No deletions executed. This report proposes only duplicate/older monolith run folders under a strict keep-list.

## Keep-list policy
- Keep all `monolith_resilient` runs for shard_001 and shard_002 (audit/publication traceability).
- Keep latest run per segment for shard_003 (resume continuity + audit).
- Candidate set = anything outside keep-list (currently expected to be minimal).

- Total monolith run dirs scanned: **15**
- Keep-list count: **15**
- Candidate delete count: **0**
- Potential reclaim: **0.0 B**

| Candidate | Shard | Segment | Size |
|---|---:|---:|---:|
