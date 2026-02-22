#!/usr/bin/env python3
import argparse, json, math
from pathlib import Path


def polyline(points, color, width=2):
    pts = ' '.join(f"{x:.1f},{y:.1f}" for x, y in points)
    return f'<polyline fill="none" stroke="{color}" stroke-width="{width}" points="{pts}" />'


def draw_line_chart(title, series, width=1400, height=320, y_label=''):
    # series: list of {name,color,data:[(ts,val)]}
    m = {'l': 80, 'r': 20, 't': 35, 'b': 40}
    all_pts = [(t, v) for s in series for (t, v) in s['data'] if v is not None]
    if not all_pts:
        return f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg"><text x="20" y="30">{title}: no data</text></svg>'
    xmin = min(t for t, _ in all_pts); xmax = max(t for t, _ in all_pts)
    ymin = min(v for _, v in all_pts); ymax = max(v for _, v in all_pts)
    if ymin == ymax:
        ymax = ymin + 1.0

    def X(t):
        return m['l'] + (t - xmin) * (width - m['l'] - m['r']) / (xmax - xmin if xmax > xmin else 1)

    def Y(v):
        return height - m['b'] - (v - ymin) * (height - m['t'] - m['b']) / (ymax - ymin)

    items = [
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#0f172a"/>',
        f'<text x="{m["l"]}" y="22" fill="#e2e8f0" font-size="16">{title}</text>',
        f'<text x="10" y="22" fill="#94a3b8" font-size="12">{y_label}</text>',
        f'<line x1="{m["l"]}" y1="{m["t"]}" x2="{m["l"]}" y2="{height-m["b"]}" stroke="#334155"/>',
        f'<line x1="{m["l"]}" y1="{height-m["b"]}" x2="{width-m["r"]}" y2="{height-m["b"]}" stroke="#334155"/>',
    ]
    # y ticks
    for i in range(5):
        v = ymin + (ymax - ymin) * i / 4
        y = Y(v)
        items.append(f'<line x1="{m["l"]}" y1="{y:.1f}" x2="{width-m["r"]}" y2="{y:.1f}" stroke="#1e293b"/>')
        items.append(f'<text x="6" y="{y+4:.1f}" fill="#94a3b8" font-size="11">{v:.1f}</text>')

    # series
    ly = 18
    for s in series:
        data = [(X(t), Y(v)) for t, v in s['data'] if v is not None]
        if data:
            items.append(polyline(data, s['color'], 2))
        items.append(f'<rect x="{width-260}" y="{ly-10}" width="10" height="10" fill="{s["color"]}"/>')
        items.append(f'<text x="{width-245}" y="{ly}" fill="#cbd5e1" font-size="12">{s["name"]}</text>')
        ly += 16

    return f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">{"".join(items)}</svg>'


def write_svg(path, body, width=1400, height=320):
    Path(path).write_text(body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dataset', required=True)
    ap.add_argument('--out-dir', required=True)
    args = ap.parse_args()

    d = json.loads(Path(args.dataset).read_text())
    rows = d.get('rows', [])
    prog = d.get('progress', [])
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    def series(key):
        return [(r['ts'], r.get(key)) for r in rows]

    charts = {
        '01_gpu_util.svg': draw_line_chart('GPU Utilization Over Time', [
            {'name': 'GPU util %', 'color': '#22c55e', 'data': series('gpu_util_pct')},
        ], y_label='%'),
        '02_gpu_memory.svg': draw_line_chart('GPU Memory Over Time', [
            {'name': 'GPU mem used MiB', 'color': '#3b82f6', 'data': series('gpu_mem_used_mib')},
            {'name': 'GPU mem total MiB', 'color': '#64748b', 'data': series('gpu_mem_total_mib')},
        ], y_label='MiB'),
        '03_gpu_power.svg': draw_line_chart('GPU Power Over Time', [
            {'name': 'GPU power W', 'color': '#ef4444', 'data': series('gpu_power_w')},
        ], y_label='W'),
        '04_cpu.svg': draw_line_chart('CPU Over Time', [
            {'name': 'Host CPU %', 'color': '#f59e0b', 'data': series('host_cpu_pct')},
            {'name': 'Inference CPU %', 'color': '#a855f7', 'data': series('proc_cpu_pct')},
        ], y_label='%'),
        '05_process_mem_uptime.svg': draw_line_chart('Process Memory & Uptime', [
            {'name': 'Proc memory %', 'color': '#14b8a6', 'data': series('proc_mem_pct')},
            {'name': 'Proc uptime s', 'color': '#84cc16', 'data': series('proc_etime_s')},
        ], y_label='mixed'),
        '06_sample_progress.svg': draw_line_chart('Cumulative Sample Progress', [
            {'name': 'Sample count', 'color': '#38bdf8', 'data': [(p['ts'], p['sample_count']) for p in prog]},
        ], y_label='count'),
    }

    # derived throughput and ETA
    thr = []
    for i in range(1, len(prog)):
        dt = max(1, prog[i]['ts'] - prog[i-1]['ts'])
        dc = prog[i]['sample_count'] - prog[i-1]['sample_count']
        thr.append((prog[i]['ts'], (dc / dt) * 60.0))
    charts['07_throughput.svg'] = draw_line_chart('Throughput (samples/min)', [
        {'name': 'samples/min', 'color': '#f97316', 'data': thr},
    ], y_label='samples/min')

    eta = []
    expected = d.get('expected_sample_count', 1)
    for t, spm in thr:
        curr = 0
        for p in prog:
            if p['ts'] <= t:
                curr = p['sample_count']
            else:
                break
        if spm and spm > 0:
            rem = max(0, expected - curr)
            eta.append((t, rem / spm))  # minutes
    charts['08_eta_minutes.svg'] = draw_line_chart('ETA (minutes, rolling)', [
        {'name': 'ETA minutes', 'color': '#eab308', 'data': eta},
    ], y_label='minutes')

    written = []
    for name, svg in charts.items():
        p = out / name
        write_svg(p, svg)
        written.append(str(p))

    summary = {
        'written_graphs': written,
        'graph_count': len(written),
        'current_sample_count': d.get('current_sample_count', 0),
        'expected_sample_count': expected,
    }
    (out / 'graph_summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
