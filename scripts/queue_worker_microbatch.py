#!/usr/bin/env python3
import argparse
import fcntl
import glob
import json
import os
import shutil
import socket
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


def utc_now():
    return datetime.now(timezone.utc)


def utc_ts(dt=None):
    dt = dt or utc_now()
    return dt.strftime('%Y%m%dT%H%M%SZ')


def run_cmd(cmd, cwd):
    p = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    return p.returncode, p.stdout, p.stderr


def parse_run_ids(text):
    run_id, run_dir = None, None
    for ln in text.splitlines():
        if ln.startswith('RUN_ID='):
            run_id = ln.split('=', 1)[1].strip()
        elif ln.startswith('RUN_DIR='):
            run_dir = ln.split('=', 1)[1].strip()
    return run_id, run_dir


def sample_count_target(run_dir: Path, target_name: str):
    pat = run_dir / 'outputs/prediction/Protenix' / target_name / 'seed_*' / 'predictions' / '*_sample_*.cif'
    return len(glob.glob(str(pat)))


def target_complete(pred_root: Path, target_name: str, expected_per_target: int) -> bool:
    pat = pred_root / target_name / 'seed_*' / 'predictions' / '*_sample_*.cif'
    return len(glob.glob(str(pat))) == expected_per_target


def copy_target(src_run_dir: Path, dst_pred_root: Path, target_name: str):
    src = src_run_dir / 'outputs/prediction/Protenix' / target_name
    if not src.exists():
        return False
    dst = dst_pred_root / target_name
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    return True


def with_locked_state(state_path: Path):
    state_path.parent.mkdir(parents=True, exist_ok=True)
    if not state_path.exists():
        raise FileNotFoundError(state_path)
    f = open(state_path, 'r+')
    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
    return f


def save_locked(f, state):
    f.seek(0)
    f.truncate(0)
    f.write(json.dumps(state, indent=2))
    f.flush()
    os.fsync(f.fileno())


def lease_one_job(state, worker_id, lease_seconds):
    now = utc_now()
    for j in sorted(state['jobs'], key=lambda x: x.get('index', 0)):
        if j['status'] in ('done', 'quarantined'):
            continue
        exp = j.get('lease_expires_at_utc')
        expired = True
        if exp:
            try:
                expired = utc_now() > datetime.strptime(exp, '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
            except Exception:
                expired = True
        if j['lease_owner'] and not expired and j['lease_owner'] != worker_id:
            continue
        j['status'] = 'running'
        j['lease_owner'] = worker_id
        j['lease_expires_at_utc'] = utc_ts(now + timedelta(seconds=lease_seconds))
        return j
    return None


def refresh_lease(state, job_id, worker_id, lease_seconds):
    for j in state['jobs']:
        if j['job_id'] == job_id and j.get('lease_owner') == worker_id and j['status'] == 'running':
            j['lease_expires_at_utc'] = utc_ts(utc_now() + timedelta(seconds=lease_seconds))
            return True
    return False


def recompute_counts(state):
    state['jobs_done'] = sum(1 for j in state['jobs'] if j['status'] == 'done')
    state['jobs_failed'] = sum(1 for j in state['jobs'] if j['status'] == 'failed')
    state['jobs_quarantined'] = sum(1 for j in state['jobs'] if j['status'] == 'quarantined')


def main():
    ap = argparse.ArgumentParser(description='Lease-based worker for micro-batch queue.')
    ap.add_argument('--queue-dir', required=True)
    ap.add_argument('--model-id', required=True)
    ap.add_argument('--checkpoint', required=True)
    ap.add_argument('--targets-dir', required=True)
    ap.add_argument('--ground-truth-dir', required=True)
    ap.add_argument('--gpu-id', default='0')
    ap.add_argument('--seeds', default='42,66,101,2024,8888')
    ap.add_argument('--samples-per-target', type=int, default=5)
    ap.add_argument('--run-prefix', default='microbatch')
    ap.add_argument('--retries', type=int, default=2)
    ap.add_argument('--lease-seconds', type=int, default=1800)
    ap.add_argument('--poll-seconds', type=int, default=5)
    ap.add_argument('--worker-id', default='')
    ap.add_argument('--aggregate-pred-root', default='')
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    queue_dir = Path(args.queue_dir).resolve()
    state_path = queue_dir / 'queue_state.json'
    pred_root = Path(args.aggregate_pred_root).resolve() if args.aggregate_pred_root else (queue_dir / 'aggregate' / 'prediction' / 'Protenix')
    pred_root.mkdir(parents=True, exist_ok=True)

    worker_id = args.worker_id or f"{socket.gethostname()}:{os.getpid()}"
    seeds = [x.strip() for x in args.seeds.split(',') if x.strip()]
    expected_per_target = len(seeds) * args.samples_per_target

    while True:
        with with_locked_state(state_path) as f:
            state = json.load(f)
            job = lease_one_job(state, worker_id, args.lease_seconds)
            recompute_counts(state)
            save_locked(f, state)

        if job is None:
            with with_locked_state(state_path) as f:
                state = json.load(f)
                pending = [j for j in state['jobs'] if j['status'] in ('pending', 'running', 'failed')]
            if not pending:
                print('QUEUE_COMPLETE')
                return 0
            time.sleep(args.poll_seconds)
            continue

        # skip if all targets already complete in aggregate
        all_done = all(target_complete(pred_root, t, expected_per_target) for t in job['target_names'])
        if all_done:
            with with_locked_state(state_path) as f:
                state = json.load(f)
                for j in state['jobs']:
                    if j['job_id'] == job['job_id']:
                        j['status'] = 'done'
                        j['lease_owner'] = None
                        j['lease_expires_at_utc'] = None
                        j['last_error'] = None
                        break
                recompute_counts(state)
                save_locked(f, state)
            continue

        cmd = [
            str(root / 'scripts' / 'hardened_launch_run.sh'),
            '--model-id', args.model_id,
            '--checkpoint', args.checkpoint,
            '--af3-input-json', job['manifest'],
            '--targets-dir', args.targets_dir,
            '--ground-truth-dir', args.ground_truth_dir,
            '--gpu-id', args.gpu_id,
            '--run-prefix', f"{args.run_prefix}_{job['job_id']}",
            '--skip-eval',
            '--protenix-seeds', args.seeds,
        ]

        # refresh lease before launch
        with with_locked_state(state_path) as f:
            state = json.load(f)
            refresh_lease(state, job['job_id'], worker_id, args.lease_seconds)
            save_locked(f, state)

        rc, so, se = run_cmd(cmd, root)
        run_id, run_dir = parse_run_ids(so + '\n' + se)

        ok = False
        err = None
        if run_dir:
            rd = Path(run_dir)
            per_target_ok = True
            for t in job['target_names']:
                if sample_count_target(rd, t) != expected_per_target:
                    per_target_ok = False
                    break
            ok = (rc == 0) and per_target_ok
            if ok:
                for t in job['target_names']:
                    copy_target(rd, pred_root, t)
            else:
                err = f"job_failed rc={rc} per_target_ok={per_target_ok}"
        else:
            err = f"missing_run_dir rc={rc}"

        with with_locked_state(state_path) as f:
            state = json.load(f)
            for j in state['jobs']:
                if j['job_id'] != job['job_id']:
                    continue
                j['attempts'] = int(j.get('attempts', 0)) + 1
                j['last_run_id'] = run_id
                j['last_run_dir'] = run_dir
                j['lease_owner'] = None
                j['lease_expires_at_utc'] = None
                if ok:
                    j['status'] = 'done'
                    j['last_error'] = None
                else:
                    if j['attempts'] > args.retries:
                        j['status'] = 'quarantined'
                    else:
                        j['status'] = 'failed'
                    j['last_error'] = err
                break
            recompute_counts(state)
            save_locked(f, state)


if __name__ == '__main__':
    raise SystemExit(main())
