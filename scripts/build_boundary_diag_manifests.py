#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'inputs/full_2023plus_shards/alphafold3_inputs_shard_001.json'
OUT = ROOT / 'inputs/diagnostics'
OUT.mkdir(parents=True, exist_ok=True)

arr = json.loads(SRC.read_text())
name_to_idx = {x.get('name'): i for i, x in enumerate(arr)}

def write_manifest(name, items):
    p = OUT / name
    p.write_text(json.dumps(items, indent=2))
    return p

t28 = arr[27] if len(arr) >= 28 else None
t29 = arr[28] if len(arr) >= 29 else None

by_name = {x.get('name'): x for x in arr}
if '8g4p-assembly1' in by_name:
    t29 = by_name['8g4p-assembly1']

if t29 is None:
    raise SystemExit('Could not locate boundary target 29 / 8g4p-assembly1 in shard_001 manifest')

m1 = write_manifest('alphafold3_inputs_diag_t29_only.json', [t29])
if t28 is None:
    raise SystemExit('Could not locate target 28 in shard_001 manifest')
m2 = write_manifest('alphafold3_inputs_diag_t28_t29.json', [t28, t29])

start = max(0, 24)
m3 = write_manifest('alphafold3_inputs_diag_t25_t29.json', arr[start:29])

report = {
    'source': str(SRC),
    'target_28': t28.get('name'),
    'target_29': t29.get('name'),
    'target_29_index_in_source': name_to_idx.get(t29.get('name')),
    'manifests': [str(m1), str(m2), str(m3)]
}
(OUT / 'boundary_diag_report.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
