# Pareto Inclusion Rules (Go/No-Go)

A shard/model row is **included** in frontier plotting only if all are true:

1. `completion_gate_ok == true`
2. `targets_completed == targets_total`
3. `actual_samples == expected_samples`
4. Quality metrics present (`quality_metric_primary` not null; secondary optional by plot type)

Rows failing any rule are excluded from final Pareto frontier and listed in an exclusions table.

Use pass-only rows from `pareto_dataset_index.json` / `pareto_dataset.csv`.
