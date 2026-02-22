#!/usr/bin/env python3
import argparse, csv, glob, json, os
from datetime import datetime
from pathlib import Path


def parse_ts(x):
    try:
        return datetime.fromisoformat(x).timestamp()
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--run-dir', required=True)
    ap.add_argument('--out', default=None)
    args = ap.parse_args()

    run = Path(args.run_dir)
    tele = run / 'logs' / 'resource_telemetry_live.csv'
    pred = run / 'outputs' / 'prediction' / 'Protenix'
    target_events = run / 'target_progress.jsonl'

    rows = []
    if tele.exists():
        with tele.open() as f:
            r = csv.DictReader(f)
            for row in r:
                ts = parse_ts(row.get('ts', ''))
                if ts is None:
                    continue
                def num(k):
                    v = (row.get(k) or '').strip()
                    try:
                        return float(v)
                    except Exception:
                        return None
                rows.append({
                    'ts': ts,
                    'gpu_util_pct': num('gpu_util_pct'),
                    'gpu_mem_used_mib': num('gpu_mem_used_mib'),
                    'gpu_mem_total_mib': num('gpu_mem_total_mib'),
                    'gpu_power_w': num('gpu_power_w'),
                    'host_cpu_pct': num('host_cpu_pct'),
                    'proc_cpu_pct': num('proc_cpu_pct'),
                    'proc_mem_pct': num('proc_mem_pct'),
                    'proc_etime_s': num('proc_etime_s'),
                    'sample_count_telemetry': num('sample_count'),
                })
    rows.sort(key=lambda x: x['ts'])

    # sample progress from files
    sample_files = glob.glob(str(pred / '*' / 'seed_*' / 'predictions' / '*_sample_*.cif'))
    mt = []
    for p in sample_files:
        try:
            mt.append(os.path.getmtime(p))
        except FileNotFoundError:
            pass
    mt.sort()

    progress = []
    c = 0
    last_bucket = None
    for t in mt:
        b = int(t // 60) * 60
        if last_bucket is None:
            last_bucket = b
        if b != last_bucket:
            progress.append({'ts': last_bucket, 'sample_count': c})
            last_bucket = b
        c += 1
    if last_bucket is not None:
        progress.append({'ts': last_bucket, 'sample_count': c})

    # target progress summary
    target_summary = {'target_started': 0, 'seed_completed': 0}
    if target_events.exists():
        for ln in target_events.read_text(errors='ignore').splitlines():
            try:
                rec = json.loads(ln)
            except Exception:
                continue
            k = rec.get('kind')
            if k in target_summary:
                target_summary[k] += 1

    out = {
        'run_dir': str(run),
        'rows': rows,
        'progress': progress,
        'current_sample_count': len(sample_files),
        'expected_sample_count': 1522 * 5 * 5,
        'target_summary': target_summary,
    }

    out_path = Path(args.out) if args.out else (run / 'logs' / 'telemetry_dataset.json')
    out_path.write_text(json.dumps(out, indent=2))
    print(str(out_path))


if __name__ == '__main__':
    main()
