#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone


def utc_ts():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def main():
    ap = argparse.ArgumentParser(description='Initialize deterministic micro-batch queue from AF3 input list.')
    ap.add_argument('--af3-input-json', required=True)
    ap.add_argument('--queue-dir', required=True)
    ap.add_argument('--batch-size', type=int, default=5)
    ap.add_argument('--max-jobs', type=int, default=0)
    args = ap.parse_args()

    queue_dir = Path(args.queue_dir).resolve()
    jobs_dir = queue_dir / 'jobs'
    manifests_dir = queue_dir / 'manifests'
    state_path = queue_dir / 'queue_state.json'
    jobs_dir.mkdir(parents=True, exist_ok=True)
    manifests_dir.mkdir(parents=True, exist_ok=True)

    items = json.loads(Path(args.af3_input_json).read_text())
    batches = [items[i:i + args.batch_size] for i in range(0, len(items), args.batch_size)]
    if args.max_jobs and args.max_jobs > 0:
        batches = batches[:args.max_jobs]

    jobs = []
    for i, batch in enumerate(batches, start=1):
        jid = f'job_{i:04d}'
        mf = manifests_dir / f'{jid}.json'
        mf.write_text(json.dumps(batch, indent=2))
        target_names = [x.get('name', f'unnamed_{k+1}') for k, x in enumerate(batch)]
        job = {
            'job_id': jid,
            'index': i,
            'manifest': str(mf),
            'target_names': target_names,
            'target_count': len(target_names),
            'status': 'pending',
            'attempts': 0,
            'lease_owner': None,
            'lease_expires_at_utc': None,
            'last_run_id': None,
            'last_run_dir': None,
            'last_error': None,
        }
        jobs.append(job)
        (jobs_dir / f'{jid}.json').write_text(json.dumps(job, indent=2))

    state = {
        'schema': 'foldbench.microbatch.queue.v1',
        'created_at_utc': utc_ts(),
        'source_af3_input_json': str(Path(args.af3_input_json).resolve()),
        'batch_size': args.batch_size,
        'job_total': len(jobs),
        'jobs_done': 0,
        'jobs_failed': 0,
        'jobs_quarantined': 0,
        'jobs': jobs,
    }
    state_path.write_text(json.dumps(state, indent=2))
    print(str(state_path))


if __name__ == '__main__':
    main()
