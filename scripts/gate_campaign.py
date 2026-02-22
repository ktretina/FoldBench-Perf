#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description='Final campaign-level fail-closed gate.')
    ap.add_argument('--campaign', required=True)
    ap.add_argument('--run-report', required=True)
    ap.add_argument('--aggregate-summary', required=True)
    args = ap.parse_args()

    campaign = json.loads(Path(args.campaign).read_text())
    report = json.loads(Path(args.run_report).read_text())
    agg = json.loads(Path(args.aggregate_summary).read_text())

    shard_count_expected = len(campaign.get('shards', []))
    shard_count_passed = sum(1 for r in report.get('results', []) if r.get('gate_ok'))
    expected_samples = sum(int(s.get('expected_samples', 0)) for s in campaign.get('shards', []))

    checks = {
        'all_shards_passed': shard_count_passed == shard_count_expected,
        'no_failed_shards_in_aggregate': len(agg.get('failed_shards', [])) == 0,
        'aggregate_unique_matches_expected': int(agg.get('unique_keys', 0)) == expected_samples,
    }

    ok = all(checks.values())
    out = {
        'schema': 'foldbench.microshard.campaign-gate.v1',
        'ok': ok,
        'checks': checks,
        'shard_count_expected': shard_count_expected,
        'shard_count_passed': shard_count_passed,
        'expected_samples': expected_samples,
        'aggregate_unique_keys': int(agg.get('unique_keys', 0)),
    }

    out_path = Path(args.aggregate_summary).resolve().parent / 'campaign_gate.json'
    out_path.write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    raise SystemExit(0 if ok else 2)


if __name__ == '__main__':
    main()
