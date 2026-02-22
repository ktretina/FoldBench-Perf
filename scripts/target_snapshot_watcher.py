#!/usr/bin/env python3
import json, subprocess, time
from pathlib import Path
import argparse

ROOT = Path(__file__).resolve().parents[1]

ap = argparse.ArgumentParser()
ap.add_argument('--run-dir', required=True)
ap.add_argument('--interval', type=int, default=10)
args = ap.parse_args()

run = Path(args.run_dir)
progress = run / 'target_progress.jsonl'
seen = set()

while True:
    status = run / 'run_status.json'
    if status.exists():
        try:
            st = json.loads(status.read_text()).get('state')
            if st in {'completed', 'failed'}:
                break
        except Exception:
            pass

    if progress.exists():
        for line in progress.read_text(errors='ignore').splitlines():
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get('kind') != 'target_started':
                continue
            key = f"{rec.get('target')}|{rec.get('seed')}|{rec.get('rank_index')}"
            if key in seen:
                continue
            seen.add(key)
            tag = f"r{rec.get('rank_index')}_{rec.get('target')}_s{rec.get('seed')}"
            tag = tag.replace('/', '_').replace(' ', '_')
            subprocess.run([
                str(ROOT / 'scripts' / 'boundary_snapshot.sh'),
                str(run),
                tag
            ], check=False)
    time.sleep(args.interval)
