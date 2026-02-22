#!/usr/bin/env python3
import argparse, json, re
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument('--model-id', required=True)
ap.add_argument('--matrix', default='/home/ktretina/.openclaw/workspace/github_projects/FoldBench/scripts/model_matrix.yaml')
ap.add_argument('--out', required=True)
args = ap.parse_args()

text = Path(args.matrix).read_text(encoding='utf-8')
blocks = re.split(r'\n\s*-\s+model_id:\s*', text)
models = []
for b in blocks[1:]:
    first_line, *rest = b.splitlines()
    model_id = first_line.strip()
    body = '\n'.join(rest)
    def pick(key):
        m = re.search(rf'^{key}:\s*(.+)$', body, re.M)
        return m.group(1).strip() if m else ''
    models.append({
        'model_id': model_id,
        'algorithm_name': pick('algorithm_name'),
        'checkpoint_name': pick('checkpoint_name'),
        'training_cutoff': pick('training_cutoff'),
        'comparability_label': pick('comparability_label'),
    })

match = next((m for m in models if m['model_id'] == args.model_id), None)
if match is None:
    raise SystemExit(f'model_id not found: {args.model_id}')

Path(args.out).write_text(json.dumps(match, indent=2), encoding='utf-8')
print(json.dumps({'ok': True, 'out': args.out, 'model_id': args.model_id}, indent=2))
