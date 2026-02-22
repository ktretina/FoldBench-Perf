#!/usr/bin/env python3
"""Matrix orchestrator for full-target Protenix benchmarking."""

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('/home/ktretina/.openclaw/workspace/github_projects/FoldBench')
MATRIX_FILE = ROOT / 'scripts' / 'model_matrix.yaml'


def parse_model_matrix(path: Path):
    models = []
    cur = None
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.rstrip()
        if not line or line.strip().startswith('#'):
            continue
        if line.strip().startswith('- model_id:'):
            if cur:
                models.append(cur)
            cur = {'model_id': line.split(':', 1)[1].strip()}
            continue
        if cur is None:
            continue
        if ':' in line:
            k, v = line.strip().split(':', 1)
            cur[k.strip()] = v.strip()
    if cur:
        models.append(cur)
    return models


def run(cmd, env=None, cwd=None):
    p = subprocess.run(cmd, cwd=cwd, env=env, text=True)
    return p.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run-id', default=f"protenix_matrix_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")
    ap.add_argument('--checkpoint-v1', required=True)
    ap.add_argument('--checkpoint-v1-20250630', required=True)
    ap.add_argument('--gpu-id', default='0')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    models = parse_model_matrix(MATRIX_FILE)
    by_id = {m['model_id']: m for m in models}
    required = ['Protenix-v1', 'Protenix-v1-20250630']
    for m in required:
        if m not in by_id:
            raise SystemExit(f'model missing in matrix: {m}')

    run_root = ROOT / 'runs' / args.run_id
    run_root.mkdir(parents=True, exist_ok=True)

    plan = {
        'run_id': args.run_id,
        'run_root': str(run_root),
        'sets': [
            {
                'set_id': 'FULL_2023PLUS',
                'af3_input_json': str(ROOT / 'inputs/full_2023plus/alphafold3_inputs.json'),
                'targets_dir': str(ROOT / 'targets'),
            },
            {
                'set_id': 'SUBSET_2024PLUS',
                'af3_input_json': str(ROOT / 'inputs/subset_2024plus/alphafold3_inputs.json'),
                'targets_dir': str(ROOT / 'targets_2024'),
            },
        ],
        'models': required,
        'dry_run': args.dry_run,
    }
    (run_root / 'matrix_plan.json').write_text(json.dumps(plan, indent=2), encoding='utf-8')

    checkpoints = {
        'Protenix-v1': args.checkpoint_v1,
        'Protenix-v1-20250630': args.checkpoint_v1_20250630,
    }

    for model_id in required:
        model_run_dir = run_root / model_id
        model_run_dir.mkdir(parents=True, exist_ok=True)

        (model_run_dir / 'foldbench_commit.txt').write_text(
            subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() + '\n',
            encoding='utf-8',
        )
        (model_run_dir / 'model_matrix.yaml').write_text(MATRIX_FILE.read_text(encoding='utf-8'), encoding='utf-8')

        label_out = model_run_dir / 'comparability.json'
        cmd_label = ['python3', str(ROOT / 'scripts/label_comparability.py'), '--model-id', model_id, '--out', str(label_out)]
        if args.dry_run:
            print('[dry-run]', ' '.join(cmd_label))
        else:
            rc = run(cmd_label, cwd=str(ROOT))
            if rc != 0:
                raise SystemExit(rc)

        for set_spec in plan['sets']:
            set_id = set_spec['set_id']
            set_out = model_run_dir / set_id
            set_out.mkdir(parents=True, exist_ok=True)

            env = os.environ.copy()
            env['PROTENIX_MODEL_ID'] = model_id
            env['PROTENIX_CHECKPOINT_PATH'] = checkpoints[model_id]
            env['GPU_ID'] = str(args.gpu_id)
            env['AF3_INPUT_JSON'] = set_spec['af3_input_json']
            env['TARGETS_DIR'] = set_spec['targets_dir']
            env['GROUND_TRUTH_DIR'] = str(ROOT / 'data/foldbench_referenced_cifs/extracted/ground_truth_20250520')
            env['OUTPUT_ROOT_DIR'] = str(set_out / 'outputs')
            env['TIME_LOG_ROOT_DIR'] = str(set_out / 'logs')

            cmd_run = [str(ROOT / 'run_full_targets.sh')]
            if args.dry_run:
                print('[dry-run]', ' '.join(cmd_run), 'for', model_id, set_id)
            else:
                rc = run(cmd_run, env=env, cwd=str(ROOT))
                if rc != 0:
                    raise SystemExit(rc)

            # summary table for this set
            summary_path = set_out / f"summary_table_{'full_2023plus' if set_id == 'FULL_2023PLUS' else '2024plus'}.csv"
            cmd_summary = [
                'python3', str(ROOT / 'task_score_summary.py'),
                '--evaluation_dir', str(set_out / 'outputs/evaluation'),
                '--target_dir', set_spec['targets_dir'],
                '--output_path', str(summary_path),
                '--algorithm_names', 'Protenix',
                '--targets',
                'interface_protein_ligand', 'interface_protein_protein', 'interface_antibody_antigen',
                'interface_protein_peptide', 'interface_protein_rna', 'interface_protein_dna',
                'monomer_protein', 'monomer_rna', 'monomer_dna',
                '--metric_type', 'rank',
            ]
            if args.dry_run:
                print('[dry-run]', ' '.join(cmd_summary))
            else:
                rc = run(cmd_summary, cwd=str(ROOT))
                if rc != 0:
                    raise SystemExit(rc)

            manifest = {
                'run_id': args.run_id,
                'model_id': model_id,
                'set_id': set_id,
                'af3_input_json': set_spec['af3_input_json'],
                'targets_dir': set_spec['targets_dir'],
                'ground_truth_dir': env['GROUND_TRUTH_DIR'],
                'output_root_dir': env['OUTPUT_ROOT_DIR'],
                'summary_csv': str(summary_path),
            }
            (set_out / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')

    print(json.dumps({'status': 'ok', 'run_root': str(run_root), 'dry_run': args.dry_run}, indent=2))


if __name__ == '__main__':
    main()
