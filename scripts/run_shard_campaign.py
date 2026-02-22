#!/usr/bin/env python3
import argparse
import json
import subprocess
from pathlib import Path
from datetime import datetime, timezone


def utc_ts():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def run_cmd(cmd, cwd=None):
    p = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    return p.returncode, p.stdout, p.stderr


def main():
    ap = argparse.ArgumentParser(description='Run deterministic micro-shards sequentially and gate each shard.')
    ap.add_argument('--campaign', required=True)
    ap.add_argument('--run-prefix', default='campaign')
    ap.add_argument('--gpu-id', default='0')
    ap.add_argument('--skip-eval', action='store_true', default=True)
    ap.add_argument('--limit-shards', type=int, default=0)
    ap.add_argument('--out-report', required=True)
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    campaign = json.loads(Path(args.campaign).read_text())
    shards = campaign.get('shards', [])
    if args.limit_shards and args.limit_shards > 0:
        shards = shards[:args.limit_shards]

    report = {
        'schema': 'foldbench.microshard.run-report.v1',
        'campaign': str(Path(args.campaign).resolve()),
        'started_at_utc': utc_ts(),
        'results': []
    }

    for s in shards:
        shard_id = s['shard_id']
        run_prefix = f"{args.run_prefix}_{shard_id}"
        cmd = [
            str(root / 'scripts' / 'hardened_launch_run.sh'),
            '--model-id', campaign['model']['model_id'],
            '--checkpoint', campaign['model']['checkpoint'],
            '--af3-input-json', s['af3_input_json'],
            '--targets-dir', campaign['dataset']['targets_dir'],
            '--ground-truth-dir', campaign['dataset']['ground_truth_dir'],
            '--gpu-id', str(args.gpu_id),
            '--run-prefix', run_prefix,
            '--protenix-seeds', ','.join(campaign['model']['seeds']),
            '--skip-eval',
        ]

        rc, out, err = run_cmd(cmd, cwd=root)
        run_id = None
        run_dir = None
        for line in (out + '\n' + err).splitlines():
            if line.startswith('RUN_ID='):
                run_id = line.split('=', 1)[1].strip()
            elif line.startswith('RUN_DIR='):
                run_dir = line.split('=', 1)[1].strip()

        gate_rc = 99
        gate_out = ''
        gate_err = ''
        if run_dir:
            gcmd = [
                str(root / 'scripts' / 'gate_shard.py'),
                '--campaign', str(Path(args.campaign).resolve()),
                '--shard-id', shard_id,
                '--run-dir', run_dir,
            ]
            gate_rc, gate_out, gate_err = run_cmd(gcmd, cwd=root)

        report['results'].append({
            'shard_id': shard_id,
            'run_id': run_id,
            'run_dir': run_dir,
            'launch_rc': rc,
            'gate_rc': gate_rc,
            'gate_ok': gate_rc == 0,
            'launch_tail': '\n'.join((out + '\n' + err).splitlines()[-20:]),
            'gate_tail': '\n'.join((gate_out + '\n' + gate_err).splitlines()[-20:]),
        })

    report['ended_at_utc'] = utc_ts()
    out_path = Path(args.out_report).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2))
    print(str(out_path))


if __name__ == '__main__':
    main()
