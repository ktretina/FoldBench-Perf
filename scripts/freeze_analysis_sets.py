#!/usr/bin/env python3
import csv, hashlib, json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('/home/ktretina/.openclaw/workspace/github_projects/FoldBench')
OUT = ROOT / 'analysis_sets'
OUT.mkdir(parents=True, exist_ok=True)


def sha256(path: Path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def collect(dir_name: str):
    d = ROOT / dir_name
    rows = {}
    for f in sorted(d.glob('*.csv')):
        with f.open('r', encoding='utf-8') as fh:
            n = max(0, sum(1 for _ in fh) - 1)
        rows[f.name] = {
            'rows': n,
            'sha256': sha256(f),
        }
    return rows

now = datetime.now(timezone.utc).isoformat()
full = {
    'analysis_set': 'FULL_2023PLUS',
    'generated_at': now,
    'source_dir': str(ROOT / 'targets'),
    'files': collect('targets'),
}
sub = {
    'analysis_set': 'SUBSET_2024PLUS',
    'generated_at': now,
    'source_dir': str(ROOT / 'targets_2024'),
    'files': collect('targets_2024'),
}

(OUT / 'ANALYSIS_SET_FULL.json').write_text(json.dumps(full, indent=2), encoding='utf-8')
(OUT / 'ANALYSIS_SET_2024.json').write_text(json.dumps(sub, indent=2), encoding='utf-8')
print(json.dumps({'full': str(OUT / 'ANALYSIS_SET_FULL.json'), 'subset': str(OUT / 'ANALYSIS_SET_2024.json')}, indent=2))
