#!/usr/bin/env python3
import argparse
import csv
import json
import subprocess
from pathlib import Path
from datetime import datetime, timezone


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def utc_now():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def parse_ts(ts: str):
    return datetime.strptime(ts, '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)


def main():
    ap = argparse.ArgumentParser(description='Build run-scoped FoldBench results tables (CSV + markdown).')
    ap.add_argument('--state-json', required=True)
    ap.add_argument('--pareto-root', required=True)
    ap.add_argument('--shard-id', required=True)
    ap.add_argument('--model-id', required=True)
    ap.add_argument('--out-dir', required=True)
    ap.add_argument('--campaign-root', default='')
    args = ap.parse_args()

    state = load_json(Path(args.state_json).resolve(), {})
    pareto_index = load_json(Path(args.pareto_root).resolve() / 'pareto_dataset_index.json', {'rows': []})

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    targets_total = int(state.get('total_targets', 0))
    targets_done = sum(1 for v in state.get('targets', {}).values() if v.get('ok'))
    expected_per_target = int(state.get('expected_per_target', 25))
    expected_samples = targets_total * expected_per_target
    credited_samples = targets_done * expected_per_target

    segs = state.get('segments', [])
    seg_rows = []
    for s in segs:
        dur = None
        if s.get('started_at_utc') and s.get('ended_at_utc'):
            dur = (parse_ts(s['ended_at_utc']) - parse_ts(s['started_at_utc'])).total_seconds()
        passed = 0
        for a in s.get('attempts', []):
            passed = max(passed, len(a.get('passed_targets', [])))
        seg_rows.append({
            'segment_index': s.get('segment_index'),
            'ok': bool(s.get('ok')),
            'targets_expected': len(s.get('targets', [])),
            'targets_passed': passed,
            'attempts': len(s.get('attempts', [])),
            'started_at_utc': s.get('started_at_utc'),
            'ended_at_utc': s.get('ended_at_utc'),
            'duration_seconds': dur,
        })

    # shard progress table
    shard_progress_csv = out_dir / 'shard_progress.csv'
    with shard_progress_csv.open('w', newline='') as f:
        cols = ['shard_id', 'model_id', 'targets_done', 'targets_total', 'credited_samples', 'expected_samples', 'segments_done', 'segments_total', 'completion_pct', 'updated_at_utc']
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerow({
            'shard_id': args.shard_id,
            'model_id': args.model_id,
            'targets_done': targets_done,
            'targets_total': targets_total,
            'credited_samples': credited_samples,
            'expected_samples': expected_samples,
            'segments_done': sum(1 for r in seg_rows if r['ok']),
            'segments_total': (targets_total + 19) // 20 if targets_total else 0,
            'completion_pct': round((100.0 * targets_done / targets_total), 2) if targets_total else 0.0,
            'updated_at_utc': utc_now(),
        })

    # segment progress table
    segment_progress_csv = out_dir / 'segment_progress.csv'
    with segment_progress_csv.open('w', newline='') as f:
        cols = ['segment_index', 'ok', 'targets_expected', 'targets_passed', 'attempts', 'started_at_utc', 'ended_at_utc', 'duration_seconds']
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in sorted(seg_rows, key=lambda x: (x['segment_index'] or 0)):
            w.writerow(r)

    # pareto rows table (all rows + current row extracted)
    pareto_rows = pareto_index.get('rows', [])
    pareto_csv = out_dir / 'pareto_rows.csv'
    with pareto_csv.open('w', newline='') as f:
        cols = [
            'shard_id', 'model_id', 'variant_label', 'targets_total', 'targets_completed', 'expected_samples', 'actual_samples',
            'completion_gate_ok', 'walltime_seconds', 'throughput_samples_per_min', 'cost_proxy_gpu_seconds',
            'quality_metric_primary', 'quality_metric_secondary', 'created_at_utc'
        ]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in pareto_rows:
            w.writerow({c: r.get(c) for c in cols})

    current = None
    for r in pareto_rows:
        if r.get('shard_id') == args.shard_id and r.get('model_id') == args.model_id:
            current = r
            break

    summary_md = out_dir / 'run_summary.md'
    lines = []
    lines.append(f"# FoldBench Run Summary ({args.shard_id} / {args.model_id})")
    lines.append("")
    lines.append(f"- Updated UTC: {utc_now()}")
    lines.append(f"- Targets: {targets_done}/{targets_total}")
    lines.append(f"- Credited samples: {credited_samples}/{expected_samples}")
    lines.append(f"- Segments complete: {sum(1 for r in seg_rows if r['ok'])}/{(targets_total + 19)//20 if targets_total else 0}")
    if current:
        lines.append(f"- Pareto gate: {current.get('completion_gate_ok')}")
        lines.append(f"- Throughput (samples/min): {current.get('throughput_samples_per_min')}")
        lines.append(f"- Quality primary: {current.get('quality_metric_primary')}")
        lines.append(f"- Quality secondary: {current.get('quality_metric_secondary')}")
    lines.append("")
    lines.append("## Segment table")
    lines.append("")
    lines.append("| seg | ok | passed/expected | attempts | duration_s |")
    lines.append("|---:|:--:|:---:|---:|---:|")
    for r in sorted(seg_rows, key=lambda x: (x['segment_index'] or 0)):
        lines.append(f"| {r['segment_index']} | {r['ok']} | {r['targets_passed']}/{r['targets_expected']} | {r['attempts']} | {r['duration_seconds']} |")

    summary_md.write_text('\n'.join(lines) + '\n')

    # GitHub-friendly README with badge-style status line.
    readme = out_dir / 'README.md'
    status = 'PASS' if (targets_done == targets_total and targets_total > 0) else 'IN_PROGRESS'
    lines2 = []
    lines2.append(f"# Results Tables — {args.shard_id} / {args.model_id}")
    lines2.append("")
    lines2.append(f"**Status:** `{status}`")
    lines2.append("")
    lines2.append(f"- Targets: **{targets_done}/{targets_total}**")
    lines2.append(f"- Segments: **{sum(1 for r in seg_rows if r['ok'])}/{(targets_total + 19)//20 if targets_total else 0}**")
    lines2.append(f"- Credited samples: **{credited_samples}/{expected_samples}**")
    if current:
        lines2.append(f"- Throughput (samples/min): **{current.get('throughput_samples_per_min')}**")
        lines2.append(f"- Pareto gate: **{current.get('completion_gate_ok')}**")
    lines2.append("")
    lines2.append("## Files")
    lines2.append("")
    lines2.append("- `shard_progress.csv`")
    lines2.append("- `segment_progress.csv`")
    lines2.append("- `pareto_rows.csv`")
    lines2.append("- `run_summary.md`")
    readme.write_text('\n'.join(lines2) + '\n')

    all_shards_csv = None
    dashboard_md = None
    if args.campaign_root:
        campaign_root = Path(args.campaign_root).resolve()
        campaign_root.mkdir(parents=True, exist_ok=True)
        all_shards_csv = campaign_root / 'all_shards_progress.csv'
        cols = [
            'shard_id','model_id','targets_done','targets_total','credited_samples','expected_samples',
            'segments_done','segments_total','completion_pct','updated_at_utc'
        ]

        # load existing rows, upsert by (shard_id, model_id)
        rows = []
        if all_shards_csv.exists():
            with all_shards_csv.open() as f:
                rdr = csv.DictReader(f)
                rows = list(rdr)
        rows = [r for r in rows if not (r.get('shard_id') == args.shard_id and r.get('model_id') == args.model_id)]
        rows.append({
            'shard_id': args.shard_id,
            'model_id': args.model_id,
            'targets_done': str(targets_done),
            'targets_total': str(targets_total),
            'credited_samples': str(credited_samples),
            'expected_samples': str(expected_samples),
            'segments_done': str(sum(1 for r in seg_rows if r['ok'])),
            'segments_total': str((targets_total + 19)//20 if targets_total else 0),
            'completion_pct': str(round((100.0 * targets_done / targets_total), 2) if targets_total else 0.0),
            'updated_at_utc': utc_now(),
        })

        with all_shards_csv.open('w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            # stable sort by shard id then model
            for r in sorted(rows, key=lambda x: (x.get('shard_id',''), x.get('model_id',''))):
                w.writerow(r)

        # refresh campaign dashboard markdown
        script = Path(__file__).resolve().parent / 'update_campaign_dashboard.py'
        p = subprocess.run([
            str(script),
            '--campaign-root', str(campaign_root),
            '--pareto-root', str(Path(args.pareto_root).resolve())
        ], capture_output=True, text=True)
        if p.returncode == 0 and p.stdout.strip():
            dashboard_md = p.stdout.strip().splitlines()[-1].strip()

    print(json.dumps({
        'shard_progress_csv': str(shard_progress_csv),
        'segment_progress_csv': str(segment_progress_csv),
        'pareto_rows_csv': str(pareto_csv),
        'summary_md': str(summary_md),
        'readme_md': str(readme),
        'all_shards_csv': str(all_shards_csv) if all_shards_csv else None,
        'campaign_dashboard_md': dashboard_md
    }, indent=2))


if __name__ == '__main__':
    main()
