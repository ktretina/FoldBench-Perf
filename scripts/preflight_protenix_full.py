#!/usr/bin/env python3
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('/home/ktretina/.openclaw/workspace/github_projects/FoldBench')
REPORT_PATH = ROOT / 'runs' / 'preflight_protenix_full.json'


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def run_cmd(cmd: str, timeout: int = 30):
    try:
        p = subprocess.run(cmd, shell=True, text=True, capture_output=True, timeout=timeout)
        return {
            'ok': p.returncode == 0,
            'returncode': p.returncode,
            'stdout': (p.stdout or '').strip(),
            'stderr': (p.stderr or '').strip(),
        }
    except Exception as e:
        return {
            'ok': False,
            'returncode': -1,
            'stdout': '',
            'stderr': f'{type(e).__name__}: {e}',
        }


def run_cmd_retry(cmd: str, timeout: int = 30, attempts: int = 3):
    last = None
    for i in range(attempts):
        last = run_cmd(cmd, timeout=timeout)
        if last.get('ok'):
            last['attempt'] = i + 1
            return last
    if last is None:
        last = {'ok': False, 'returncode': -1, 'stdout': '', 'stderr': 'no attempts'}
    last['attempt'] = attempts
    return last


def sha256(path: Path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def parse_model_matrix(path: Path):
    text = path.read_text(encoding='utf-8')
    blocks = re.split(r'\n\s*-\s+model_id:\s*', text)
    out = []
    for b in blocks[1:]:
        first, *rest = b.splitlines()
        model_id = first.strip()
        body = '\n'.join(rest)

        def pick(k):
            m = re.search(rf'^\s*{k}:\s*(.+)$', body, re.M)
            return m.group(1).strip() if m else ''

        out.append({
            'model_id': model_id,
            'algorithm_name': pick('algorithm_name'),
            'checkpoint_name': pick('checkpoint_name'),
            'training_cutoff': pick('training_cutoff'),
            'comparability_label': pick('comparability_label'),
        })
    return out


def check_required_files():
    required = [
        'RUNBOOK_PROTENIX_FULL.md',
        'PROTOCOL.md',
        'fairness_matrix.yaml',
        'telemetry_schema_v1.json',
        'scripts/model_matrix.yaml',
        'scripts/check_pareto_artifacts.py',
        'scripts/freeze_analysis_sets.py',
        'scripts/label_comparability.py',
    ]
    missing = [p for p in required if not (ROOT / p).exists()]
    return {'ok': len(missing) == 0, 'missing': missing}


def check_model_matrix():
    p = ROOT / 'scripts/model_matrix.yaml'
    if not p.exists():
        return {'ok': False, 'error': 'missing model_matrix.yaml'}
    models = parse_model_matrix(p)
    ids = {m['model_id'] for m in models}
    required_ids = {'Protenix-v1', 'Protenix-v1-20250630'}
    labels_ok = all(m.get('comparability_label') in {'strict_comparable', 'reference_only'} for m in models)
    fields_ok = all(all(m.get(k) for k in ('checkpoint_name', 'training_cutoff', 'comparability_label')) for m in models)
    return {
        'ok': required_ids.issubset(ids) and labels_ok and fields_ok,
        'model_ids': sorted(ids),
        'required_ids': sorted(required_ids),
        'labels_ok': labels_ok,
        'fields_ok': fields_ok,
    }


def check_analysis_sets():
    full = ROOT / 'analysis_sets/ANALYSIS_SET_FULL.json'
    sub = ROOT / 'analysis_sets/ANALYSIS_SET_2024.json'
    targets_2024 = ROOT / 'targets_2024'
    if not full.exists() or not sub.exists() or not targets_2024.exists():
        return {
            'ok': False,
            'missing': [str(p) for p in [full, sub, targets_2024] if not p.exists()]
        }

    issues = []
    for manifest in [full, sub]:
        try:
            data = json.loads(manifest.read_text(encoding='utf-8'))
            src = Path(data['source_dir'])
            for name, meta in (data.get('files') or {}).items():
                f = src / name
                if not f.exists():
                    issues.append(f'missing_file:{f}')
                    continue
                with f.open('r', encoding='utf-8') as fh:
                    rows = max(0, sum(1 for _ in fh) - 1)
                if rows != meta.get('rows'):
                    issues.append(f'row_mismatch:{f}:{rows}!={meta.get("rows")}')
                digest = sha256(f)
                if digest != meta.get('sha256'):
                    issues.append(f'sha_mismatch:{f}')
        except Exception as e:
            issues.append(f'manifest_parse_error:{manifest}:{e}')

    return {'ok': len(issues) == 0, 'issues': issues}


def check_runtime():
    checks = {}
    checks['apptainer'] = run_cmd('command -v apptainer')
    if not checks['apptainer']['ok']:
        checks['apptainer_base_env'] = run_cmd("bash -lc 'source /home/ktretina/miniconda/etc/profile.d/conda.sh && conda run -n base apptainer --version'")
        if checks['apptainer_base_env']['ok']:
            checks['apptainer'] = {
                'ok': True,
                'returncode': 0,
                'stdout': checks['apptainer_base_env']['stdout'],
                'stderr': checks['apptainer_base_env']['stderr'],
            }
    checks['nvidia_smi'] = run_cmd('command -v nvidia-smi')
    checks['gpu_query'] = run_cmd('nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader')
    checks['nvidia_container_cli'] = run_cmd('command -v nvidia-container-cli')
    apptainer_target = '/home/ktretina/.openclaw/workspace/github_projects/FoldBench/algorithms/Protenix/container.sandbox'
    if not Path(apptainer_target).exists():
        apptainer_target = '/home/ktretina/.openclaw/workspace/github_projects/FoldBench/algorithms/Protenix/container.sif'
    checks['apptainer_nvccli_cuda_target'] = {'ok': True, 'path': apptainer_target}
    checks['apptainer_nvccli_cuda'] = run_cmd_retry(
        f"bash -lc '/home/ktretina/miniconda/bin/apptainer exec --nvccli {apptainer_target} nvidia-smi -L'",
        timeout=45,
        attempts=3,
    )
    checks['conda_sh_exists'] = {'ok': Path('/home/ktretina/miniconda/etc/profile.d/conda.sh').exists()}
    checks['conda_env_list'] = run_cmd("bash -lc 'source /home/ktretina/miniconda/etc/profile.d/conda.sh && conda env list'")
    checks['ost_help'] = run_cmd("bash -lc 'source /home/ktretina/miniconda/etc/profile.d/conda.sh && conda activate foldbench && ost --help | head -n 5'")

    env_ok = checks['conda_env_list']['ok'] and ('foldbench' in checks['conda_env_list']['stdout'])
    ok = all([
        checks['apptainer']['ok'],
        checks['nvidia_smi']['ok'],
        checks['gpu_query']['ok'],
        checks['nvidia_container_cli']['ok'],
        checks['apptainer_nvccli_cuda']['ok'],
        checks['conda_sh_exists']['ok'],
        env_ok,
        checks['ost_help']['ok'],
    ])
    checks['foldbench_env_present'] = env_ok
    checks['ok'] = ok
    return checks


def check_targets_schema(target_dir: Path):
    issues = []
    counts = {}
    for f in sorted(target_dir.glob('*.csv')):
        # Ignore enrichment artifacts; validate benchmark target csvs only.
        if not (f.name.startswith('interface_') or f.name.startswith('monomer_')):
            continue
        try:
            with f.open('r', encoding='utf-8', newline='') as fh:
                reader = csv.DictReader(fh)
                headers = reader.fieldnames or []
                rows = list(reader)
            counts[f.name] = len(rows)
            if 'pdb_id' not in headers:
                issues.append(f'missing_pdb_id:{f.name}')
            if f.name.startswith('monomer_'):
                if 'chain_id' not in headers:
                    issues.append(f'missing_chain_id:{f.name}')
        except Exception as e:
            issues.append(f'parse_error:{f.name}:{e}')
    return {'ok': len(issues) == 0, 'issues': issues, 'counts': counts}


def main():
    report = {
        'generated_at': now_iso(),
        'root': str(ROOT),
        'checks': {}
    }

    report['checks']['required_files'] = check_required_files()
    report['checks']['model_matrix'] = check_model_matrix()
    report['checks']['analysis_sets'] = check_analysis_sets()
    report['checks']['runtime'] = check_runtime()
    report['checks']['targets_full'] = check_targets_schema(ROOT / 'targets')
    report['checks']['targets_2024'] = check_targets_schema(ROOT / 'targets_2024') if (ROOT / 'targets_2024').exists() else {'ok': False, 'issues': ['targets_2024_missing']}

    overall_ok = all(v.get('ok', False) for v in report['checks'].values())
    report['status'] = 'pass' if overall_ok else 'fail'

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding='utf-8')

    print(json.dumps({'status': report['status'], 'report': str(REPORT_PATH)}, indent=2))
    sys.exit(0 if overall_ok else 2)


if __name__ == '__main__':
    main()
