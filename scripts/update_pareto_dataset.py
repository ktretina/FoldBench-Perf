#!/usr/bin/env python3
import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def utc_ts() -> str:
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def parse_ts(ts: str):
    return datetime.strptime(ts, '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def count_samples(pred_root: Path) -> int:
    import glob
    return len(glob.glob(str(pred_root / '*/seed_*/predictions/*_sample_*.cif')))


def try_float(v):
    try:
        return float(v)
    except Exception:
        return None


def infer_quality_metrics(csv_path: Path, primary_col: str, secondary_col: str):
    if not csv_path or not csv_path.exists():
        return None, None, None
    rows = []
    with csv_path.open() as f:
        rdr = csv.DictReader(f)
        for r in rdr:
            rows.append(r)
    if not rows:
        return None, None, f'quality csv empty: {csv_path}'

    # If not provided, attempt common FoldBench column names.
    cand_primary = [primary_col] if primary_col else [
        'DockQ', 'dockq', 'ranking_score', 'score', 'mean_score'
    ]
    cand_secondary = [secondary_col] if secondary_col else [
        'rmsd', 'RMSD', 'tm_score', 'TMscore', 'latency_sec'
    ]

    pvals = None
    pcol_used = None
    for c in cand_primary:
        if c and c in rows[0]:
            vals = [try_float(r.get(c)) for r in rows]
            vals = [v for v in vals if v is not None]
            if vals:
                pvals = vals
                pcol_used = c
                break

    svals = None
    scol_used = None
    for c in cand_secondary:
        if c and c in rows[0]:
            vals = [try_float(r.get(c)) for r in rows]
            vals = [v for v in vals if v is not None]
            if vals:
                svals = vals
                scol_used = c
                break

    q1 = mean(pvals) if pvals else None
    q2 = mean(svals) if svals else None
    note = f'quality from {csv_path}; primary_col={pcol_used}; secondary_col={scol_used}'
    return q1, q2, note


def main():
    ap = argparse.ArgumentParser(description='Create/update Pareto artifact rows from a completed shard state.')
    ap.add_argument('--state-json', required=True)
    ap.add_argument('--aggregate-pred-root', required=True)
    ap.add_argument('--af3-input-json', required=True)
    ap.add_argument('--shard-id', required=True)
    ap.add_argument('--model-id', required=True)
    ap.add_argument('--checkpoint', required=True)
    ap.add_argument('--seeds', required=True)
    ap.add_argument('--samples-per-target', type=int, required=True)
    ap.add_argument('--segment-size', type=int, required=True)
    ap.add_argument('--pareto-root', required=True)
    ap.add_argument('--variant-label', default='Protenix-v1')
    ap.add_argument('--quality-summary-csv', default='')
    ap.add_argument('--quality-primary-column', default='')
    ap.add_argument('--quality-secondary-column', default='')
    args = ap.parse_args()

    state_path = Path(args.state_json).resolve()
    pred_root = Path(args.aggregate_pred_root).resolve()
    af3 = Path(args.af3_input_json).resolve()
    ckpt = Path(args.checkpoint).resolve()
    pareto_root = Path(args.pareto_root).resolve()
    pareto_root.mkdir(parents=True, exist_ok=True)

    st = load_json(state_path, {})
    items = load_json(af3, [])
    targets_total = len(items)
    targets_completed = sum(1 for v in st.get('targets', {}).values() if v.get('ok'))

    seeds = [s.strip() for s in args.seeds.split(',') if s.strip()]
    expected_samples = targets_total * len(seeds) * args.samples_per_target
    actual_samples = count_samples(pred_root)
    completion_gate_ok = (targets_completed == targets_total and actual_samples == expected_samples)

    segs = st.get('segments', [])
    segments_total = (targets_total + args.segment_size - 1) // args.segment_size
    segments_completed = sum(1 for s in segs if s.get('ok'))

    walltime_seconds = 0.0
    for s in segs:
        if not s.get('ok'):
            continue
        if s.get('started_at_utc') and s.get('ended_at_utc'):
            walltime_seconds += (parse_ts(s['ended_at_utc']) - parse_ts(s['started_at_utc'])).total_seconds()

    throughput = (actual_samples / (walltime_seconds / 60.0)) if walltime_seconds > 0 else 0.0

    quality_csv = Path(args.quality_summary_csv).resolve() if args.quality_summary_csv else None
    q1, q2, qnote = infer_quality_metrics(quality_csv, args.quality_primary_column, args.quality_secondary_column)

    row = {
        'schema': 'foldbench.pareto.artifact.v1',
        'artifact_version': 1,
        'shard_id': args.shard_id,
        'model_id': args.model_id,
        'variant_label': args.variant_label,
        'checkpoint_path': str(ckpt),
        'checkpoint_sha256': sha256(ckpt),
        'af3_input_json': str(af3),
        'af3_input_sha256': sha256(af3),
        'targets_total': targets_total,
        'targets_completed': targets_completed,
        'segment_size': args.segment_size,
        'segments_total': segments_total,
        'segments_completed': segments_completed,
        'seeds': seeds,
        'samples_per_target': args.samples_per_target,
        'expected_samples': expected_samples,
        'actual_samples': actual_samples,
        'completion_gate_ok': completion_gate_ok,
        'walltime_seconds': walltime_seconds,
        'throughput_samples_per_min': throughput,
        'cost_proxy_gpu_seconds': walltime_seconds,
        'quality_summary_path': str(quality_csv) if quality_csv else None,
        'quality_metric_primary': q1,
        'quality_metric_secondary': q2,
        'quality_notes': qnote if qnote else 'Populate after evaluation/summary stage.',
        'resume_state_json': str(state_path),
        'aggregate_pred_root': str(pred_root),
        'created_at_utc': utc_ts(),
    }

    # write per-shard canonical artifact
    shards_dir = pareto_root / 'shards'
    shards_dir.mkdir(parents=True, exist_ok=True)
    shard_path = shards_dir / f"{args.shard_id}_{args.model_id}.json"
    shard_path.write_text(json.dumps(row, indent=2))

    # upsert index json
    index_path = pareto_root / 'pareto_dataset_index.json'
    index = load_json(index_path, {'schema': 'foldbench.pareto.dataset.index.v1', 'rows': []})
    rows = [r for r in index.get('rows', []) if not (r.get('shard_id') == args.shard_id and r.get('model_id') == args.model_id)]
    rows.append(row)
    index['rows'] = rows
    index_path.write_text(json.dumps(index, indent=2))

    # refresh csv snapshot
    csv_path = pareto_root / 'pareto_dataset.csv'
    cols = [
        'shard_id','model_id','variant_label','targets_total','targets_completed','segments_total','segments_completed',
        'expected_samples','actual_samples','completion_gate_ok','walltime_seconds','throughput_samples_per_min',
        'cost_proxy_gpu_seconds','checkpoint_sha256','af3_input_sha256','created_at_utc'
    ]
    with csv_path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c) for c in cols})

    print(json.dumps({
        'shard_artifact': str(shard_path),
        'index': str(index_path),
        'csv': str(csv_path),
        'completion_gate_ok': completion_gate_ok,
        'targets_completed': targets_completed,
        'targets_total': targets_total,
        'actual_samples': actual_samples,
        'expected_samples': expected_samples
    }, indent=2))


if __name__ == '__main__':
    main()
