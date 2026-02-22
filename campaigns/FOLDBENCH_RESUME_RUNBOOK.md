# FoldBench Resume Runbook

## Preconditions
1. Confirm GPU path and checkpoint availability.
2. Ensure no stale monolith/watchdog/supervisor processes are running.
3. Re-enable desired cron jobs deliberately.

## Resume manual (single-step)
```bash
bash /home/ktretina/.openclaw/workspace/github_projects/FoldBench/scripts/auto_continue_shards.sh
```

## Resume continuous
Enable cron job: `FoldBench auto-continue shards every 10m`.

## Validation after resume
1. Confirm active process chain exists for expected shard.
2. Confirm telemetry dataset rebuild succeeds.
3. Confirm resume_state progresses (`DONE_TARGETS`, `SEGMENTS_RECORDED`).

## Rollback
If unstable, disable auto-continue cron and run shard manually via `run_monolith_segmented.py` under watchdog with explicit shard input.
