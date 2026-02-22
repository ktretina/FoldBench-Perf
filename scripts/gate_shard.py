#!/usr/bin/env python3
import argparse
import glob
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description='Fail-closed gate for one micro-shard run.')
    ap.add_argument('--campaign', required=True, help='Campaign manifest from campaign_init.py')
    ap.add_argument('--shard-id', required=True)
    ap.add_argument('--run-dir', required=True)
    ap.add_argument('--require-exact-samples', action='store_true', default=True)
    args = ap.parse_args()

    campaign = json.loads(Path(args.campaign).read_text())
    run = Path(args.run_dir)
    status_path = run / 'run_status.json'
    launch_manifest_path = run / 'launch_manifest.json'

    shard = None
    for s in campaign.get('shards', []):
        if s.get('shard_id') == args.shard_id:
            shard = s
            break
    if shard is None:
        raise SystemExit(f'shard-id not found in campaign: {args.shard_id}')

    status = {}
    state = 'missing'
    if status_path.exists():
        try:
            status = json.loads(status_path.read_text())
            state = status.get('state', 'unknown')
        except Exception:
            state = 'invalid_json'

    launch_manifest = {}
    if launch_manifest_path.exists():
        try:
            launch_manifest = json.loads(launch_manifest_path.read_text())
        except Exception:
            pass

    sample_count = len(glob.glob(str(run / 'outputs/prediction/Protenix/*/seed_*/predictions/*_sample_*.cif')))

    checks = {
        'state_completed': state == 'completed',
        'samples_exact': sample_count == int(shard['expected_samples']),
        'checkpoint_sha_match': launch_manifest.get('checkpoint_sha256') == campaign['model']['checkpoint_sha256'],
        'af3_sha_match': launch_manifest.get('af3_input_sha256') == shard['af3_input_sha256'],
        'model_id_match': launch_manifest.get('model_id') == campaign['model']['model_id'],
    }

    ok = all(checks.values())
    out = {
        'ok': ok,
        'shard_id': args.shard_id,
        'run_dir': str(run),
        'checks': checks,
        'state': state,
        'sample_count': sample_count,
        'expected_samples': int(shard['expected_samples']),
        'status': status,
        'launch_manifest': launch_manifest,
    }

    p = run / 'shard_gate.json'
    p.write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    raise SystemExit(0 if ok else 2)


if __name__ == '__main__':
    main()
