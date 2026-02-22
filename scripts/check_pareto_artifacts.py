#!/usr/bin/env python3
import argparse, json
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument('--run-dir', required=True)
args = ap.parse_args()
rd = Path(args.run_dir)

required = [
    rd / 'summary_table_full_2023plus.csv',
    rd / 'summary_table_2024plus.csv',
    rd / 'timing_summary.json',
    rd / 'protenix_timing.jsonl',
    rd / 'phase_walltime_full.json',
    rd / 'manifest.json',
    rd / 'comparability.json',
]
missing = [str(p) for p in required if not p.exists()]

print(json.dumps({
    'run_dir': str(rd),
    'ok': len(missing) == 0,
    'missing': missing
}, indent=2))

raise SystemExit(0 if not missing else 1)
