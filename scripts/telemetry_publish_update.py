#!/usr/bin/env python3
import argparse, json
from datetime import datetime, timezone
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run-dir', required=True)
    ap.add_argument('--out-md', default=None)
    args = ap.parse_args()

    run = Path(args.run_dir)
    ds = run / 'logs' / 'telemetry_dataset.json'
    gs = run / 'logs' / 'graphs' / 'graph_summary.json'
    d = json.loads(ds.read_text()) if ds.exists() else {}
    g = json.loads(gs.read_text()) if gs.exists() else {}

    now = datetime.now(timezone.utc).isoformat()
    cur = d.get('current_sample_count', 0)
    exp = d.get('expected_sample_count', 0)
    pct = (100.0 * cur / exp) if exp else 0.0

    lines = []
    lines.append(f"Telemetry update ({now})")
    lines.append(f"Progress: {cur}/{exp} samples ({pct:.2f}%)")
    lines.append("Graphs:")
    for p in g.get('written_graphs', []):
        lines.append(f"- {p}")

    md = '\n'.join(lines) + '\n'
    out = Path(args.out_md) if args.out_md else (run / 'logs' / 'telemetry_update.md')
    out.write_text(md)
    print(str(out))


if __name__ == '__main__':
    main()
