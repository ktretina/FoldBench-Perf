#!/usr/bin/env python3
import argparse
import csv
import json
import time
from datetime import datetime
from pathlib import Path
from urllib import request, error

RCSB_GRAPHQL_URL = "https://data.rcsb.org/graphql"


def now_iso():
    return datetime.utcnow().isoformat() + "Z"


def normalize_entry_id(pdb_id: str) -> str:
    # FoldBench IDs are typically like "8e3r-assembly1".
    base = (pdb_id or "").strip().split("-")[0]
    return base.upper()


def load_cache(cache_path: Path):
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_cache(cache_path: Path, cache_obj: dict):
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache_obj, indent=2, ensure_ascii=False), encoding="utf-8")


def query_release_date(entry_id: str, timeout: int = 20):
    gql = {
        "query": "query($id:String!){entry(entry_id:$id){rcsb_accession_info{initial_release_date}}}",
        "variables": {"id": entry_id},
    }
    data = json.dumps(gql).encode("utf-8")
    req = request.Request(
        RCSB_GRAPHQL_URL,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "FoldBench-derive-2024-subset/1.0"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8", errors="ignore"))
    if payload.get("errors"):
        return None, "graphql_error", payload.get("errors")
    entry = (((payload.get("data") or {}).get("entry") or {}))
    if not entry:
        return None, "not_found", None
    info = (entry.get("rcsb_accession_info") or {})
    release = info.get("initial_release_date")
    if not release:
        return None, "missing_release_date", None
    # Keep date only
    return str(release)[:10], "ok", None


def fetch_release_dates(entry_ids, cache_obj, retries=4, sleep_base=1.2):
    stats = {
        "api_calls": 0,
        "cache_hits": 0,
        "resolved": 0,
        "failed": 0,
    }

    for idx, entry_id in enumerate(sorted(entry_ids), 1):
        if entry_id in cache_obj and cache_obj[entry_id].get("status") == "ok":
            stats["cache_hits"] += 1
            continue

        last_err = None
        for attempt in range(retries):
            try:
                stats["api_calls"] += 1
                release_date, status, detail = query_release_date(entry_id)
                cache_obj[entry_id] = {
                    "status": status,
                    "release_date": release_date,
                    "detail": detail,
                    "updated_at": now_iso(),
                }
                if status == "ok":
                    stats["resolved"] += 1
                else:
                    stats["failed"] += 1
                last_err = None
                break
            except error.HTTPError as e:
                last_err = f"HTTPError {e.code}"
            except error.URLError as e:
                last_err = f"URLError {e.reason}"
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"

            if attempt < retries - 1:
                time.sleep(sleep_base * (2 ** attempt))

        if last_err is not None:
            cache_obj[entry_id] = {
                "status": "network_error",
                "release_date": None,
                "detail": last_err,
                "updated_at": now_iso(),
            }
            stats["failed"] += 1

        if idx % 100 == 0:
            print(f"[progress] enriched {idx}/{len(entry_ids)} unique entry IDs")

    return stats


def parse_date(d: str):
    return datetime.strptime(d, "%Y-%m-%d").date()


def derive_subset(targets_dir: Path, out_dir: Path, cache_path: Path, cutoff_date: str):
    cutoff = parse_date(cutoff_date)
    out_dir.mkdir(parents=True, exist_ok=True)

    target_files = sorted(targets_dir.glob("*.csv"))
    if not target_files:
        raise RuntimeError(f"No target CSV files found in {targets_dir}")

    all_rows = {}
    unique_entry_ids = set()

    for f in target_files:
        rows = []
        with f.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            fieldnames = reader.fieldnames or []
            for row in reader:
                pdb_id = (row.get("pdb_id") or "").strip()
                entry_id = normalize_entry_id(pdb_id)
                row["__entry_id"] = entry_id
                rows.append(row)
                if entry_id:
                    unique_entry_ids.add(entry_id)
        all_rows[f.name] = {
            "fieldnames": fieldnames,
            "rows": rows,
        }

    print(f"[progress] loaded {len(target_files)} target files")
    print(f"[progress] discovered {len(unique_entry_ids)} unique entry IDs")

    cache_obj = load_cache(cache_path)
    enrich_stats = fetch_release_dates(unique_entry_ids, cache_obj)
    save_cache(cache_path, cache_obj)
    print("[progress] enrichment complete and cache updated")

    release_map_rows = []
    unresolved = []
    for eid in sorted(unique_entry_ids):
        rec = cache_obj.get(eid, {})
        status = rec.get("status", "missing")
        release_date = rec.get("release_date")
        release_map_rows.append({
            "entry_id": eid,
            "release_date": release_date or "",
            "status": status,
            "detail": json.dumps(rec.get("detail"), ensure_ascii=False) if rec.get("detail") is not None else "",
        })
        if status != "ok":
            unresolved.append({"entry_id": eid, "status": status, "detail": rec.get("detail")})

    with (out_dir / "release_date_map.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["entry_id", "release_date", "status", "detail"])
        writer.writeheader()
        writer.writerows(release_map_rows)

    per_file_counts = {}

    for fname, payload in all_rows.items():
        fieldnames = payload["fieldnames"]
        rows = payload["rows"]

        kept = []
        for row in rows:
            eid = row.get("__entry_id", "")
            rec = cache_obj.get(eid, {})
            if rec.get("status") != "ok":
                continue
            try:
                rd = parse_date(rec.get("release_date"))
            except Exception:
                continue
            if rd >= cutoff:
                clean = {k: v for k, v in row.items() if k != "__entry_id"}
                kept.append(clean)

        out_file = out_dir / fname
        with out_file.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(kept)

        per_file_counts[fname] = {
            "original_rows": len(rows),
            "kept_rows": len(kept),
        }

    report = {
        "generated_at": now_iso(),
        "cutoff_date": cutoff_date,
        "targets_dir": str(targets_dir),
        "out_dir": str(out_dir),
        "cache_path": str(cache_path),
        "target_files": len(target_files),
        "unique_entry_ids": len(unique_entry_ids),
        "enrichment_stats": enrich_stats,
        "unresolved_count": len(unresolved),
        "unresolved_examples": unresolved[:20],
        "per_file_counts": per_file_counts,
    }

    (out_dir / "derivation_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("[progress] wrote filtered targets + report")
    print(json.dumps(report, indent=2, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description="Derive FoldBench 2024 subset by release date enrichment from RCSB metadata.")
    ap.add_argument("--targets-dir", default="/home/ktretina/.openclaw/workspace/github_projects/FoldBench/targets")
    ap.add_argument("--out-dir", default="/home/ktretina/.openclaw/workspace/github_projects/FoldBench/targets_2024")
    ap.add_argument("--cache-path", default="/home/ktretina/.openclaw/workspace/github_projects/FoldBench/targets_2024/release_date_cache.json")
    ap.add_argument("--cutoff-date", default="2024-01-01")
    args = ap.parse_args()

    derive_subset(
        targets_dir=Path(args.targets_dir),
        out_dir=Path(args.out_dir),
        cache_path=Path(args.cache_path),
        cutoff_date=args.cutoff_date,
    )


if __name__ == "__main__":
    main()
