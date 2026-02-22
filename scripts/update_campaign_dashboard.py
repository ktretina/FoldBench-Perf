#!/usr/bin/env python3
import argparse
import csv
import json
import glob
import subprocess
from pathlib import Path
from datetime import datetime, timezone


def utc():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def active_process_present() -> bool:
    out = subprocess.getoutput("ps -eo cmd | grep -E 'monolith_watchdog.sh|monolith_supervisor.sh|run_monolith_segmented.py|hardened_launch_run.sh --model-id Protenix-v1|runner/inference.py' | grep -v grep")
    return bool(out.strip())


def latest_sample_count() -> int:
    runs = sorted(glob.glob('/home/ktretina/.openclaw/workspace/github_projects/FoldBench/runs/monolith_resilient_s*_seg*_Protenix-v1_targets_*/targets'))
    if not runs:
        return 0
    run = Path(runs[-1])
    files = glob.glob(str(run / 'outputs/prediction/Protenix/*/seed_*/predictions/*_sample_*.cif'))
    return len(files)


def load_monitor_state(campaign_root: Path):
    st = campaign_root / 'dashboard_state.json'
    if st.exists():
        try:
            return st, json.loads(st.read_text())
        except Exception:
            return st, {}
    return st, {}


def estimate_eta_hours(progress_rows, pareto_rows, active_sample_count):
    # Throughput basis from pass-gated pareto rows (samples/min)
    thr = []
    for r in pareto_rows:
        try:
            if r.get('completion_gate_ok') is True and r.get('throughput_samples_per_min'):
                thr.append(float(r.get('throughput_samples_per_min')))
        except Exception:
            pass
    if not thr:
        return None, None

    spm = sum(thr) / len(thr)

    # Remaining samples over tracked shards only
    remaining = 0
    for r in progress_rows:
        try:
            exp = int(float(r.get('expected_samples', 0)))
            got = int(float(r.get('credited_samples', 0)))
            rem = max(0, exp - got)
            remaining += rem
        except Exception:
            pass

    # account for in-flight samples not yet credited
    if active_sample_count and remaining > 0:
        # subtract only up to one shard budget heuristic
        remaining = max(0, remaining - int(active_sample_count))

    if spm <= 0:
        return None, None
    return remaining / spm / 60.0, spm


def main():
    ap = argparse.ArgumentParser(description='Update campaign dashboard markdown from shard progress + pareto dataset.')
    ap.add_argument('--campaign-root', required=True)
    ap.add_argument('--pareto-root', required=True)
    ap.add_argument('--total-shards', type=int, default=16)
    ap.add_argument('--default-shard-expected-samples', type=int, default=2500)
    args = ap.parse_args()

    campaign_root = Path(args.campaign_root).resolve()
    pareto_root = Path(args.pareto_root).resolve()
    campaign_root.mkdir(parents=True, exist_ok=True)

    all_shards = campaign_root / 'all_shards_progress.csv'
    pareto_idx = load_json(pareto_root / 'pareto_dataset_index.json', {'rows': []})

    rows = []
    if all_shards.exists():
        with all_shards.open() as f:
            rows = list(csv.DictReader(f))

    # badge status: on-track / degraded / blocked
    now_ts = utc()
    now_epoch = int(datetime.now(timezone.utc).timestamp())
    active = active_process_present()
    sc = latest_sample_count()
    st_path, st = load_monitor_state(campaign_root)
    last_sc = int(st.get('last_sample_count', sc))
    last_change_epoch = int(st.get('last_change_epoch', now_epoch))
    if sc > last_sc:
        last_change_epoch = now_epoch

    stalled = active and (now_epoch - last_change_epoch >= 1800)
    if active and not stalled:
        badge = '🟢 on-track'
    elif active and stalled:
        badge = '🟡 degraded'
    else:
        badge = '🔴 blocked'

    st_path.write_text(json.dumps({
        'last_sample_count': sc,
        'last_change_epoch': last_change_epoch,
        'updated_at_utc': now_ts,
        'badge': badge
    }, indent=2))

    idx_rows = sorted(pareto_idx.get('rows', []), key=lambda x: (x.get('shard_id', ''), x.get('model_id', '')))
    eta_hours, spm_basis = estimate_eta_hours(rows, idx_rows, sc)

    # Optional full-campaign ETA extrapolation.
    eta_full_hours = None
    if spm_basis and spm_basis > 0:
        tracked_expected = 0
        tracked_credited = 0
        for r in rows:
            try:
                tracked_expected += int(float(r.get('expected_samples', 0)))
                tracked_credited += int(float(r.get('credited_samples', 0)))
            except Exception:
                pass
        remaining_tracked = max(0, tracked_expected - tracked_credited - int(sc or 0))
        untracked = max(0, int(args.total_shards) - len(rows))
        remaining_untracked = untracked * int(args.default_shard_expected_samples)
        remaining_full = remaining_tracked + remaining_untracked
        eta_full_hours = remaining_full / spm_basis / 60.0

    lines = []
    lines.append('# FoldBench Campaign Dashboard')
    lines.append('')
    if eta_hours is not None:
        lines.append(f'- Status: **{badge} · ETA (tracked shards): ~{eta_hours:.1f}h**')
    else:
        lines.append(f'- Status: **{badge}**')
    lines.append(f'- Updated UTC: `{now_ts}`')
    if spm_basis is not None:
        lines.append(f'- Throughput basis: `{spm_basis:.3f} samples/min` (pass-gated rows)')
    if eta_full_hours is not None:
        lines.append(f'- ETA (full campaign est., {args.total_shards} shards): `~{eta_full_hours:.1f}h`')
    lines.append('')

    completed = 0
    total = len(rows)
    for r in rows:
        try:
            if float(r.get('completion_pct', 0)) >= 100.0:
                completed += 1
        except Exception:
            pass

    lines.append(f'- Shards tracked: **{total}**')
    lines.append(f'- Shards complete: **{completed}/{total}**')
    lines.append('')

    lines.append('## Shard Progress')
    lines.append('')
    lines.append('| Shard | Model | Targets | Samples | Segments | Completion | Updated |')
    lines.append('|---|---|---:|---:|---:|---:|---|')
    for r in sorted(rows, key=lambda x: (x.get('shard_id', ''), x.get('model_id', ''))):
        lines.append(
            f"| {r.get('shard_id')} | {r.get('model_id')} | {r.get('targets_done')}/{r.get('targets_total')} | "
            f"{r.get('credited_samples')}/{r.get('expected_samples')} | {r.get('segments_done')}/{r.get('segments_total')} | "
            f"{r.get('completion_pct')}% | {r.get('updated_at_utc')} |"
        )

    lines.append('')
    lines.append('## Pareto Rows (pass-only status)')
    lines.append('')
    lines.append('| Shard | Model | Gate | Targets | Samples | Throughput (samples/min) | Quality1 | Quality2 |')
    lines.append('|---|---|---|---:|---:|---:|---:|---:|')

    for r in idx_rows:
        lines.append(
            f"| {r.get('shard_id')} | {r.get('model_id')} | {r.get('completion_gate_ok')} | "
            f"{r.get('targets_completed')}/{r.get('targets_total')} | {r.get('actual_samples')}/{r.get('expected_samples')} | "
            f"{r.get('throughput_samples_per_min')} | {r.get('quality_metric_primary')} | {r.get('quality_metric_secondary')} |"
        )

    out = campaign_root / 'CAMPAIGN_DASHBOARD.md'
    out.write_text('\n'.join(lines) + '\n')
    print(str(out))


if __name__ == '__main__':
    main()
