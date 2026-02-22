#!/usr/bin/env python3
import argparse
import json
import shutil
import subprocess
from pathlib import Path
from datetime import datetime, timezone
import glob


def utc_ts():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def run_cmd(cmd, cwd):
    p = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    return p.returncode, p.stdout, p.stderr


def parse_run_ids(text):
    run_id = None
    run_dir = None
    for ln in text.splitlines():
        if ln.startswith('RUN_ID='):
            run_id = ln.split('=', 1)[1].strip()
        if ln.startswith('RUN_DIR='):
            run_dir = ln.split('=', 1)[1].strip()
    return run_id, run_dir


def sample_count(run_dir: Path):
    return len(glob.glob(str(run_dir / 'outputs/prediction/Protenix/*/seed_*/predictions/*_sample_*.cif')))


def copy_target_outputs(src_run_dir: Path, dst_pred_root: Path):
    src_root = src_run_dir / 'outputs/prediction/Protenix'
    if not src_root.exists():
        return 0
    copied = 0
    for target_dir in src_root.iterdir():
        if not target_dir.is_dir():
            continue
        dst_target = dst_pred_root / target_dir.name
        if dst_target.exists():
            shutil.rmtree(dst_target)
        shutil.copytree(target_dir, dst_target)
        copied += 1
    return copied


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def save_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2))


def is_target_complete(pred_root: Path, target_name: str, expected_per_target: int) -> bool:
    files = glob.glob(str(pred_root / target_name / 'seed_*' / 'predictions' / '*_sample_*.cif'))
    return len(files) == expected_per_target


def normalize_stale_running(run_dir: Path):
    rs = run_dir / 'run_status.json'
    if not rs.exists():
        return
    st = load_json(rs, {})
    if st.get('state') != 'running':
        return
    # If marked running but no relevant process exists, mark failed-stale
    chk = subprocess.getoutput(
        "ps -eo cmd | grep -E 'runner/inference.py|run_full_targets.sh|hardened_launch_run.sh' | grep -v grep"
    ).strip()
    if not chk:
        st['state'] = 'failed'
        st['failure_class'] = 'stale_running_reconciled'
        st['ended_at_utc'] = utc_ts()
        save_json(rs, st)


def main():
    ap = argparse.ArgumentParser(description='Per-target isolated fallback runner for a shard AF3 manifest (resumable).')
    ap.add_argument('--af3-input-json', required=True)
    ap.add_argument('--model-id', required=True)
    ap.add_argument('--checkpoint', required=True)
    ap.add_argument('--targets-dir', required=True)
    ap.add_argument('--ground-truth-dir', required=True)
    ap.add_argument('--gpu-id', default='0')
    ap.add_argument('--seeds', default='42,66,101,2024,8888')
    ap.add_argument('--samples-per-target', type=int, default=5)
    ap.add_argument('--run-prefix', default='isolated_fallback')
    ap.add_argument('--out-dir', required=True)
    ap.add_argument('--limit-targets', type=int, default=0)
    ap.add_argument('--retries', type=int, default=1)
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    out = Path(args.out_dir).resolve()
    manifests_dir = out / 'manifests'
    pred_root = out / 'prediction' / 'Protenix'
    state_path = out / 'resume_state.json'
    report_path = out / 'per_target_fallback_report.json'
    manifests_dir.mkdir(parents=True, exist_ok=True)
    pred_root.mkdir(parents=True, exist_ok=True)

    items = json.loads(Path(args.af3_input_json).read_text())
    if args.limit_targets and args.limit_targets > 0:
        items = items[:args.limit_targets]

    seeds = [s.strip() for s in args.seeds.split(',') if s.strip()]
    expected_per_target = len(seeds) * args.samples_per_target

    state = load_json(state_path, {
        'schema': 'foldbench.per-target-fallback.state.v1',
        'created_at_utc': utc_ts(),
        'targets': {}
    })

    report = load_json(report_path, {
        'schema': 'foldbench.per-target-fallback.v1',
        'started_at_utc': utc_ts(),
        'source_af3_input_json': str(Path(args.af3_input_json).resolve()),
        'model_id': args.model_id,
        'checkpoint': str(Path(args.checkpoint).resolve()),
        'seeds': args.seeds,
        'samples_per_target': args.samples_per_target,
        'targets_total': len(items),
        'results': []
    })

    result_by_name = {r.get('target'): r for r in report.get('results', [])}

    for i, item in enumerate(items, start=1):
        name = item.get('name', f'target_{i:03d}')
        one_manifest = manifests_dir / f'{i:03d}_{name}.json'
        if not one_manifest.exists():
            one_manifest.write_text(json.dumps([item], indent=2))

        # Fast-path skip if already complete in aggregated prediction tree.
        if is_target_complete(pred_root, name, expected_per_target):
            rec = result_by_name.get(name, {
                'index': i,
                'target': name,
                'manifest': str(one_manifest),
                'attempts': []
            })
            rec['ok'] = True
            rec['skipped_existing'] = True
            result_by_name[name] = rec
            state['targets'][name] = {'ok': True, 'skipped_existing': True, 'updated_at_utc': utc_ts()}
            save_json(state_path, state)
            continue

        rec = result_by_name.get(name, {
            'index': i,
            'target': name,
            'manifest': str(one_manifest),
            'attempts': []
        })

        # Resume attempt counter from existing report.
        attempt = len(rec.get('attempts', []))
        ok = False
        if rec.get('ok') is True:
            ok = True

        while attempt <= args.retries and not ok:
            attempt += 1
            cmd = [
                str(root / 'scripts' / 'hardened_launch_run.sh'),
                '--model-id', args.model_id,
                '--checkpoint', args.checkpoint,
                '--af3-input-json', str(one_manifest),
                '--targets-dir', args.targets_dir,
                '--ground-truth-dir', args.ground_truth_dir,
                '--gpu-id', args.gpu_id,
                '--run-prefix', f"{args.run_prefix}_{i:03d}",
                '--skip-eval',
                '--protenix-seeds', args.seeds,
            ]
            rc, so, se = run_cmd(cmd, root)
            run_id, run_dir = parse_run_ids(so + '\n' + se)

            sc = 0
            run_state = None
            if run_dir:
                rdp = Path(run_dir)
                normalize_stale_running(rdp)
                sc = sample_count(rdp)
                run_status = load_json(rdp / 'run_status.json', {})
                run_state = run_status.get('state')

            pass_now = ((rc == 0 or run_state == 'completed') and sc == expected_per_target)
            rec.setdefault('attempts', []).append({
                'attempt': attempt,
                'launch_rc': rc,
                'run_id': run_id,
                'run_dir': run_dir,
                'run_state': run_state,
                'sample_count': sc,
                'expected_sample_count': expected_per_target,
                'ok': pass_now,
                'tail': '\n'.join((so + '\n' + se).splitlines()[-20:])
            })

            if pass_now and run_dir:
                copy_target_outputs(Path(run_dir), pred_root)
                ok = True

            # Persist progress after every attempt.
            rec['ok'] = ok
            result_by_name[name] = rec
            report['results'] = list(result_by_name.values())
            state['targets'][name] = {'ok': ok, 'attempts': attempt, 'updated_at_utc': utc_ts()}
            save_json(report_path, report)
            save_json(state_path, state)

        if not ok:
            # Continue with remaining targets; campaign gate will fail closed.
            pass

    total_samples = len(glob.glob(str(pred_root / '*/seed_*/predictions/*_sample_*.cif')))
    expected_total = len(items) * expected_per_target
    report['ended_at_utc'] = utc_ts()
    report['aggregate'] = {
        'expected_total_samples': expected_total,
        'actual_total_samples': total_samples,
        'ok': total_samples == expected_total and all(r.get('ok') for r in report['results'])
    }

    save_json(report_path, report)
    save_json(state_path, state)
    print(str(report_path))
    raise SystemExit(0 if report['aggregate']['ok'] else 2)


if __name__ == '__main__':
    main()
