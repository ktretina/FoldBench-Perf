#!/usr/bin/env python3
import argparse, glob, json, hashlib
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run-dir', required=True)
    ap.add_argument('--expected-samples', type=int, required=True)
    ap.add_argument('--expected-state', default='completed')
    ap.add_argument('--require-exact-samples', action='store_true', help='Require sample_count == expected_samples (not >=).')
    ap.add_argument('--expected-checkpoint-sha256', default='')
    ap.add_argument('--expected-af3-sha256', default='')
    args = ap.parse_args()

    run = Path(args.run_dir)
    status = run / 'run_status.json'
    launch_manifest = run / 'launch_manifest.json'

    state = 'missing'
    status_obj = {}
    if status.exists():
        try:
            status_obj = json.loads(status.read_text())
            state = status_obj.get('state', 'unknown')
        except Exception:
            state = 'invalid_json'

    sample_count = len(glob.glob(str(run / 'outputs/prediction/Protenix/*/seed_*/predictions/*_sample_*.cif')))

    manifest_obj = {}
    manifest_ok = launch_manifest.exists()
    if manifest_ok:
        try:
            manifest_obj = json.loads(launch_manifest.read_text())
        except Exception:
            manifest_ok = False

    checks = {
        'state_ok': state == args.expected_state,
        'samples_ok': (sample_count == args.expected_samples) if args.require_exact_samples else (sample_count >= args.expected_samples),
        'manifest_present': manifest_ok,
        'checkpoint_sha_ok': True,
        'af3_sha_ok': True,
    }

    if args.expected_checkpoint_sha256:
        checks['checkpoint_sha_ok'] = manifest_obj.get('checkpoint_sha256') == args.expected_checkpoint_sha256
    if args.expected_af3_sha256:
        checks['af3_sha_ok'] = manifest_obj.get('af3_input_sha256') == args.expected_af3_sha256

    ok = all(checks.values())
    out = {
        'ok': ok,
        'checks': checks,
        'state': state,
        'sample_count': sample_count,
        'expected_samples': args.expected_samples,
        'require_exact_samples': args.require_exact_samples,
        'status': status_obj,
        'manifest': manifest_obj,
    }
    (run / 'completion_gate.json').write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    raise SystemExit(0 if ok else 2)


if __name__ == '__main__':
    main()
