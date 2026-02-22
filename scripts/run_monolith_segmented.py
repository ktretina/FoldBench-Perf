#!/usr/bin/env python3
import argparse
import glob
import json
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from monolith_resume_state import ensure_state, atomic_write_json


def utc_ts():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def run_cmd(cmd, cwd):
    p = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    return p.returncode, p.stdout, p.stderr


def parse_run(text):
    rid = None
    rdir = None
    for ln in text.splitlines():
        if ln.startswith('RUN_ID='):
            rid = ln.split('=', 1)[1].strip()
        elif ln.startswith('RUN_DIR='):
            rdir = ln.split('=', 1)[1].strip()
    return rid, rdir


def target_count_in_run(run_dir: Path, target_name: str):
    pat = run_dir / 'outputs/prediction/Protenix' / target_name / 'seed_*' / 'predictions' / '*_sample_*.cif'
    return len(glob.glob(str(pat)))


def agg_target_count(agg_root: Path, target_name: str):
    pat = agg_root / target_name / 'seed_*' / 'predictions' / '*_sample_*.cif'
    return len(glob.glob(str(pat)))


def copy_target(run_dir: Path, agg_root: Path, target_name: str):
    import shutil
    src = run_dir / 'outputs/prediction/Protenix' / target_name
    if not src.exists():
        return False
    dst = agg_root / target_name
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    return True


def main():
    ap = argparse.ArgumentParser(description='Segmented monolith runner with deterministic resume state.')
    ap.add_argument('--af3-input-json', required=True)
    ap.add_argument('--model-id', required=True)
    ap.add_argument('--checkpoint', required=True)
    ap.add_argument('--targets-dir', required=True)
    ap.add_argument('--ground-truth-dir', required=True)
    ap.add_argument('--gpu-id', default='0')
    ap.add_argument('--seeds', default='42,66,101,2024,8888')
    ap.add_argument('--samples-per-target', type=int, default=5)
    ap.add_argument('--segment-size', type=int, default=20)
    ap.add_argument('--max-segments', type=int, default=0)
    ap.add_argument('--run-prefix', default='monolith_segmented')
    ap.add_argument('--state-json', required=True)
    ap.add_argument('--work-dir', required=True)
    ap.add_argument('--aggregate-pred-root', required=True)
    ap.add_argument('--retries', type=int, default=1)
    ap.add_argument('--shard-id', default='shard_001')
    ap.add_argument('--pareto-root', default='')
    ap.add_argument('--variant-label', default='Protenix-v1')
    ap.add_argument('--quality-summary-csv', default='')
    ap.add_argument('--quality-primary-column', default='')
    ap.add_argument('--quality-secondary-column', default='')
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    work_dir = Path(args.work_dir).resolve()
    agg_root = Path(args.aggregate_pred_root).resolve()
    st_path = Path(args.state_json).resolve()
    manifests_dir = work_dir / 'segment_manifests'
    manifests_dir.mkdir(parents=True, exist_ok=True)
    agg_root.mkdir(parents=True, exist_ok=True)

    items = json.loads(Path(args.af3_input_json).read_text())
    seeds = [s.strip() for s in args.seeds.split(',') if s.strip()]
    expected_per_target = len(seeds) * args.samples_per_target
    st = ensure_state(st_path, args.af3_input_json, len(items), expected_per_target)

    # Pre-mark already complete from aggregate
    for i, item in enumerate(items, start=1):
        n = item.get('name', f'target_{i:03d}')
        if agg_target_count(agg_root, n) == expected_per_target:
            st['targets'][n] = {'ok': True, 'updated_at_utc': utc_ts(), 'source': 'aggregate_existing'}
    atomic_write_json(st_path, st)

    segments = [items[i:i+args.segment_size] for i in range(0, len(items), args.segment_size)]
    seg_count = 0
    for idx, seg in enumerate(segments, start=1):
        names = [x.get('name', f'target_{k+1}') for k, x in enumerate(seg)]
        pending = [n for n in names if not st.get('targets', {}).get(n, {}).get('ok')]
        if not pending:
            continue

        seg_count += 1
        if args.max_segments and seg_count > args.max_segments:
            break

        manifest_items = [x for x in seg if x.get('name') in pending]
        mf = manifests_dir / f'segment_{idx:03d}.json'
        mf.write_text(json.dumps(manifest_items, indent=2))

        attempt = 0
        ok = False
        seg_rec = {'segment_index': idx, 'started_at_utc': utc_ts(), 'targets': pending, 'attempts': []}
        while attempt <= args.retries and not ok:
            attempt += 1
            cmd = [
                str(root / 'scripts' / 'hardened_launch_run.sh'),
                '--model-id', args.model_id,
                '--checkpoint', args.checkpoint,
                '--af3-input-json', str(mf),
                '--targets-dir', args.targets_dir,
                '--ground-truth-dir', args.ground_truth_dir,
                '--gpu-id', args.gpu_id,
                '--run-prefix', f"{args.run_prefix}_seg{idx:03d}",
                '--skip-eval',
                '--protenix-seeds', args.seeds,
            ]
            rc, so, se = run_cmd(cmd, root)
            rid, rdir = parse_run(so + '\n' + se)

            pass_targets = []
            if rdir:
                rd = Path(rdir)
                for n in pending:
                    if target_count_in_run(rd, n) == expected_per_target:
                        if copy_target(rd, agg_root, n):
                            pass_targets.append(n)

            for n in pass_targets:
                st['targets'][n] = {
                    'ok': True,
                    'updated_at_utc': utc_ts(),
                    'segment_index': idx,
                    'run_id': rid,
                    'run_dir': rdir,
                }

            ok = len(pass_targets) == len(pending)
            seg_rec['attempts'].append({
                'attempt': attempt,
                'launch_rc': rc,
                'run_id': rid,
                'run_dir': rdir,
                'passed_targets': pass_targets,
                'expected_targets': pending,
                'ok': ok,
                'tail': '\n'.join((so + '\n' + se).splitlines()[-20:])
            })
            st['updated_at_utc'] = utc_ts()
            atomic_write_json(st_path, st)

        seg_rec['ended_at_utc'] = utc_ts()
        seg_rec['ok'] = ok
        st.setdefault('segments', []).append(seg_rec)
        st['updated_at_utc'] = utc_ts()
        atomic_write_json(st_path, st)

    # final status
    done = sum(1 for v in st.get('targets', {}).values() if v.get('ok'))

    # Auto-feed Pareto dataset + run results tables when requested.
    if args.pareto_root:
        pareto_root = str(Path(args.pareto_root).resolve())
        pcmd = [
            str(root / 'scripts' / 'update_pareto_dataset.py'),
            '--state-json', str(st_path),
            '--aggregate-pred-root', str(agg_root),
            '--af3-input-json', str(Path(args.af3_input_json).resolve()),
            '--shard-id', args.shard_id,
            '--model-id', args.model_id,
            '--checkpoint', str(Path(args.checkpoint).resolve()),
            '--seeds', args.seeds,
            '--samples-per-target', str(args.samples_per_target),
            '--segment-size', str(args.segment_size),
            '--pareto-root', pareto_root,
            '--variant-label', args.variant_label,
        ]
        if args.quality_summary_csv:
            pcmd.extend(['--quality-summary-csv', args.quality_summary_csv])
        if args.quality_primary_column:
            pcmd.extend(['--quality-primary-column', args.quality_primary_column])
        if args.quality_secondary_column:
            pcmd.extend(['--quality-secondary-column', args.quality_secondary_column])
        prc, pout, perr = run_cmd(pcmd, root)
        print(pout.strip())
        if prc != 0:
            print(perr.strip())

        tcmd = [
            str(root / 'scripts' / 'update_run_results_tables.py'),
            '--state-json', str(st_path),
            '--pareto-root', pareto_root,
            '--shard-id', args.shard_id,
            '--model-id', args.model_id,
            '--out-dir', str(Path(args.work_dir).resolve() / 'results_tables'),
            '--campaign-root', str(Path(pareto_root).resolve())
        ]
        trc, tout, terr = run_cmd(tcmd, root)
        print(tout.strip())
        if trc != 0:
            print(terr.strip())

    print(json.dumps({'done_targets': done, 'total_targets': len(items), 'state_json': str(st_path)}, indent=2))
    return 0 if done == len(items) else 2


if __name__ == '__main__':
    raise SystemExit(main())
