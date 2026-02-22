#!/usr/bin/env python3
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def utc_ts():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def main():
    ap = argparse.ArgumentParser(description='Initialize a deterministic micro-shard campaign manifest.')
    ap.add_argument('--name', required=True)
    ap.add_argument('--manifest', required=True, help='Shard manifest.json path (from build_shards.py).')
    ap.add_argument('--af3-root', required=True, help='Root directory containing per-shard AF3 json files.')
    ap.add_argument('--checkpoint', required=True)
    ap.add_argument('--model-id', required=True)
    ap.add_argument('--seeds', default='42,66,101,2024,8888')
    ap.add_argument('--samples-per-target', type=int, default=5)
    ap.add_argument('--n-cycle', type=int, default=10)
    ap.add_argument('--n-step', type=int, default=200)
    ap.add_argument('--targets-dir', required=True)
    ap.add_argument('--ground-truth-dir', required=True)
    ap.add_argument('--out', required=True, help='Output campaign manifest json')
    args = ap.parse_args()

    shard_manifest_path = Path(args.manifest).resolve()
    af3_root = Path(args.af3_root).resolve()
    checkpoint = Path(args.checkpoint).resolve()
    targets_dir = Path(args.targets_dir).resolve()
    ground_truth_dir = Path(args.ground_truth_dir).resolve()

    if not shard_manifest_path.exists():
        raise SystemExit(f'missing shard manifest: {shard_manifest_path}')
    if not checkpoint.exists():
        raise SystemExit(f'missing checkpoint: {checkpoint}')
    if not af3_root.exists():
        raise SystemExit(f'missing af3 root: {af3_root}')

    shard_manifest = json.loads(shard_manifest_path.read_text())
    seeds = [s.strip() for s in args.seeds.split(',') if s.strip()]
    if not seeds:
        raise SystemExit('seeds cannot be empty')

    shards_out = []
    for s in shard_manifest.get('shards', []):
        shard_id = s['shard_id']
        shard_size = int(s['size'])
        af3_path = af3_root / f'alphafold3_inputs_{shard_id}.json'
        if not af3_path.exists():
            # fallback for custom naming: ..._<NNN>.json
            n = shard_id.split('_')[-1]
            alt = list(af3_root.glob(f'*{n}.json'))
            if len(alt) == 1:
                af3_path = alt[0]
            else:
                raise SystemExit(f'cannot resolve AF3 shard json for {shard_id} under {af3_root}')

        expected_samples = shard_size * len(seeds) * int(args.samples_per_target)
        shards_out.append({
            'shard_id': shard_id,
            'size': shard_size,
            'af3_input_json': str(af3_path),
            'af3_input_sha256': sha256(af3_path),
            'expected_samples': expected_samples,
        })

    out = {
        'schema': 'foldbench.microshard.campaign.v1',
        'name': args.name,
        'created_at_utc': utc_ts(),
        'model': {
            'model_id': args.model_id,
            'checkpoint': str(checkpoint),
            'checkpoint_sha256': sha256(checkpoint),
            'seeds': seeds,
            'samples_per_target': int(args.samples_per_target),
            'n_cycle': int(args.n_cycle),
            'n_step': int(args.n_step),
        },
        'dataset': {
            'shard_manifest': str(shard_manifest_path),
            'targets_dir': str(targets_dir),
            'ground_truth_dir': str(ground_truth_dir),
            'total_targets': int(shard_manifest.get('total_targets', 0)),
            'shard_size': int(shard_manifest.get('shard_size', 0)),
        },
        'shards': shards_out,
    }

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2))
    print(str(out_path))


if __name__ == '__main__':
    main()
