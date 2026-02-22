#!/usr/bin/env python3
import argparse
import glob
import json
import shutil
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description='Aggregate pass-only shard outputs with dedup + coverage report.')
    ap.add_argument('--run-report', required=True)
    ap.add_argument('--out-dir', required=True)
    args = ap.parse_args()

    report = json.loads(Path(args.run_report).read_text())
    out = Path(args.out_dir).resolve()
    pred_out = out / 'prediction' / 'Protenix'
    pred_out.mkdir(parents=True, exist_ok=True)

    seen = set()
    copied = 0
    skipped_dupe = 0
    failed_shards = []

    for r in report.get('results', []):
        if not r.get('gate_ok'):
            failed_shards.append(r.get('shard_id'))
            continue
        run_dir = Path(r['run_dir'])
        files = glob.glob(str(run_dir / 'outputs/prediction/Protenix/*/seed_*/predictions/*_sample_*.cif'))
        for f in files:
            p = Path(f)
            # key: target + seed + sample filename
            key = (p.parts[-4], p.parts[-3], p.name)
            if key in seen:
                skipped_dupe += 1
                continue
            seen.add(key)
            # keep source hierarchy target/seed/predictions/file
            rel = Path(*p.parts[-4:])
            dst = pred_out / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dst)
            copied += 1

    summary = {
        'schema': 'foldbench.microshard.aggregate.v1',
        'run_report': str(Path(args.run_report).resolve()),
        'copied_files': copied,
        'skipped_duplicates': skipped_dupe,
        'unique_keys': len(seen),
        'failed_shards': failed_shards,
    }
    (out / 'aggregate_summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
