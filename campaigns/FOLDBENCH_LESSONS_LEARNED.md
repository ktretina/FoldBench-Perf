# FoldBench Lessons Learned (to date)

1. **Completion-gated accounting is essential**: only finalized segments/shards should be counted for scientific validity.
2. **Resilient segmented monolith > micro-batch for this environment**: fewer moving parts while retaining restartability.
3. **Two-layer resilience (watchdog + supervisor)** recovers from abrupt process loss, but can create restart noise after completion if not disabled.
4. **Cron hygiene matters**: completion must disable shard-specific restart loops to avoid pointless restarts.
5. **GPU runtime enforcement**: true GPU path with strict CUDA visibility checks remains mandatory.
6. **Pareto/results/dashboard auto-feed reduced manual errors** and kept campaign metadata synchronized.
7. **Quality metrics ingestion is dependency-bound**: until quality CSVs exist, Pareto quality fields remain null.
8. **Telemetry expected_sample_count can be campaign-global** in current scripts; interpret per-segment progress with current counters and resume state.
