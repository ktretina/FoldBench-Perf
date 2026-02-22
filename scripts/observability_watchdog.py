#!/usr/bin/env python3
import csv, glob, json, re, subprocess, time
from datetime import datetime, timezone
from pathlib import Path


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def sh(cmd):
    p = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def read_sample_count(pred_root: Path) -> int:
    return len(glob.glob(str(pred_root / '*' / 'seed_*' / 'predictions' / '*_sample_*.cif')))


def get_inference_proc():
    rc, out, _ = sh("ps -eo pid,ppid,etimes,pcpu,pmem,cmd | grep -E 'runner/inference.py' | grep -v grep | head -n1")
    if rc != 0 or not out:
        return None
    parts = out.split(None, 5)
    if len(parts) < 6:
        return None
    return {
        'pid': int(parts[0]),
        'ppid': int(parts[1]),
        'etime_s': int(float(parts[2])),
        'cpu_pct': float(parts[3]),
        'mem_pct': float(parts[4]),
        'cmd': parts[5],
    }


def get_gpu():
    rc, out, _ = sh("nvidia-smi --query-gpu=name,utilization.gpu,memory.used,memory.total,power.draw --format=csv,noheader,nounits | head -n1")
    if rc != 0 or not out:
        return None
    parts = [x.strip() for x in out.split(',')]
    if len(parts) < 5:
        return None
    return {
        'name': parts[0],
        'util_pct': float(parts[1]),
        'mem_used_mib': float(parts[2]),
        'mem_total_mib': float(parts[3]),
        'power_w': float(parts[4]),
    }


def snapshot_forensics(run_dir: Path, logs: Path, reason: str, sample_count: int):
    ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    snap_dir = logs / 'forensics' / f'snapshot_{ts}'
    snap_dir.mkdir(parents=True, exist_ok=True)

    cmds = {
        'ps_tree.txt': "ps -eo pid,ppid,etime,pcpu,pmem,rss,vsz,cmd | grep -E 'runner/inference.py|run_full_targets.sh|apptainer|python' | grep -v grep",
        'nvidia_smi_q.txt': "nvidia-smi -q",
        'last_run_log_tail.txt': f"tail -n 200 {run_dir / 'logs' / 'run.log'}",
        'last_protenix_time_tail.txt': f"tail -n 200 {run_dir / 'logs' / 'Protenix_time.log'}",
    }
    for name, cmd in cmds.items():
        rc, out, err = sh(cmd)
        (snap_dir / name).write_text((out + ('\n' + err if err else '')).strip() + '\n')

    proc = get_inference_proc()
    if proc:
        pid = proc['pid']
        for rel in ['status', 'limits', 'cmdline']:
            p = Path(f'/proc/{pid}/{rel}')
            if p.exists():
                try:
                    (snap_dir / f'proc_{pid}_{rel}.txt').write_text(p.read_text(errors='ignore'))
                except Exception:
                    pass

    meta = {
        'ts': now_iso(),
        'reason': reason,
        'sample_count': sample_count,
        'snapshot_dir': str(snap_dir),
    }
    (snap_dir / 'meta.json').write_text(json.dumps(meta, indent=2))
    return str(snap_dir)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--run-dir', required=True)
    ap.add_argument('--interval', type=int, default=20)
    ap.add_argument('--stall-seconds', type=int, default=900)
    ap.add_argument('--no-proc-grace-seconds', type=int, default=180)
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    logs = run_dir / 'logs'
    logs.mkdir(parents=True, exist_ok=True)

    telemetry = logs / 'resource_telemetry_live.csv'
    events = logs / 'watchdog_events.jsonl'
    pid_tree = run_dir / 'pid_tree.json'
    status_path = run_dir / 'run_status.json'

    pred_root = run_dir / 'outputs' / 'prediction' / 'Protenix'
    protenix_time_log = run_dir / 'logs' / 'Protenix_time.log'
    target_events = run_dir / 'target_progress.jsonl'
    seen_keys = set()

    rank_line = re.compile(r"\[Rank 0 \((\d+)/(\d+)\)\] ([^\s]+) \[seed:(\d+)\]")
    success_line = re.compile(r"\[Rank 0\] ([^\s]+) \[seed:(\d+)\] succeeded")

    if not telemetry.exists():
        with telemetry.open('w', newline='') as f:
            w = csv.writer(f)
            w.writerow([
                'ts','host_uptime_s','host_cpu_pct','sample_count',
                'proc_pid','proc_ppid','proc_etime_s','proc_cpu_pct','proc_mem_pct',
                'gpu_name','gpu_util_pct','gpu_mem_used_mib','gpu_mem_total_mib','gpu_power_w'
            ])

    last_growth_ts = time.time()
    last_count = read_sample_count(pred_root)
    no_proc_since = None
    last_snapshot_sig = None

    def emit_event(kind, payload):
        rec = {'ts': now_iso(), 'kind': kind, **payload}
        with events.open('a') as f:
            f.write(json.dumps(rec) + '\n')

    emit_event('watchdog_started', {
        'interval_s': args.interval,
        'stall_seconds': args.stall_seconds,
        'no_proc_grace_seconds': args.no_proc_grace_seconds,
        'initial_sample_count': last_count
    })

    while True:
        ts = now_iso()
        host_uptime = None
        try:
            host_uptime = int(float(Path('/proc/uptime').read_text().split()[0]))
        except Exception:
            pass

        rc, out, _ = sh("top -bn1 | awk '/^%Cpu\\(s\\):/ {print 100-$8}'")
        host_cpu = float(out) if rc == 0 and out else None

        proc = get_inference_proc()
        gpu = get_gpu()
        sample_count = read_sample_count(pred_root)

        if sample_count > last_count:
            last_count = sample_count
            last_growth_ts = time.time()

        if proc:
            pid_tree.write_text(json.dumps({'ts': ts, 'inference': proc}, indent=2))
            no_proc_since = None
        else:
            if no_proc_since is None:
                no_proc_since = time.time()

        with telemetry.open('a', newline='') as f:
            w = csv.writer(f)
            w.writerow([
                ts, host_uptime, host_cpu, sample_count,
                proc['pid'] if proc else '', proc['ppid'] if proc else '', proc['etime_s'] if proc else '', proc['cpu_pct'] if proc else '', proc['mem_pct'] if proc else '',
                gpu['name'] if gpu else '', gpu['util_pct'] if gpu else '', gpu['mem_used_mib'] if gpu else '', gpu['mem_total_mib'] if gpu else '', gpu['power_w'] if gpu else ''
            ])

        # parse progress clues from Protenix log (best-effort)
        if protenix_time_log.exists():
            try:
                lines = protenix_time_log.read_text(errors='ignore').splitlines()[-400:]
                for ln in lines:
                    m = rank_line.search(ln)
                    if m:
                        k = f"start:{m.group(3)}:{m.group(4)}"
                        if k not in seen_keys:
                            seen_keys.add(k)
                            rec = {
                                'ts': now_iso(),
                                'kind': 'target_started',
                                'rank_index': int(m.group(1)),
                                'rank_total': int(m.group(2)),
                                'target': m.group(3),
                                'seed': m.group(4),
                            }
                            with target_events.open('a') as f:
                                f.write(json.dumps(rec) + '\n')
                    s = success_line.search(ln)
                    if s:
                        k = f"ok:{s.group(1)}:{s.group(2)}"
                        if k not in seen_keys:
                            seen_keys.add(k)
                            rec = {'ts': now_iso(), 'kind': 'seed_completed', 'target': s.group(1), 'seed': s.group(2)}
                            with target_events.open('a') as f:
                                f.write(json.dumps(rec) + '\n')
            except Exception:
                pass

        state = None
        if status_path.exists():
            try:
                state = json.loads(status_path.read_text()).get('state')
            except Exception:
                state = None

        stalled = (time.time() - last_growth_ts) > args.stall_seconds
        no_proc_running = state == 'running' and no_proc_since is not None and (time.time() - no_proc_since) > args.no_proc_grace_seconds

        if state == 'running' and stalled:
            sig = f"stall:{sample_count}"
            if sig != last_snapshot_sig:
                snap_dir = snapshot_forensics(run_dir, logs, 'stall_detected', sample_count)
                emit_event('stall_detected', {
                    'sample_count': sample_count,
                    'seconds_since_growth': int(time.time() - last_growth_ts),
                    'snapshot_dir': snap_dir,
                })
                last_snapshot_sig = sig

        if no_proc_running:
            sig = f"no_proc:{sample_count}"
            if sig != last_snapshot_sig:
                snap_dir = snapshot_forensics(run_dir, logs, 'no_inference_process_detected', sample_count)
                emit_event('process_missing_while_running', {
                    'sample_count': sample_count,
                    'seconds_without_inference_proc': int(time.time() - no_proc_since),
                    'snapshot_dir': snap_dir,
                })
                last_snapshot_sig = sig

        if state in {'completed', 'failed'}:
            emit_event('watchdog_stopped', {'final_state': state, 'final_sample_count': sample_count})
            break

        time.sleep(args.interval)


if __name__ == '__main__':
    main()
