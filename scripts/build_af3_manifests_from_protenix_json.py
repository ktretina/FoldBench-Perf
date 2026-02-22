#!/usr/bin/env python3
import argparse
import csv
import glob
import hashlib
import json
import os
from typing import Dict, List, Tuple

SEEDS = ["42", "66", "101", "2024", "8888"]


def load_target_ids(target_dir: str) -> List[str]:
    ids = []
    for path in sorted(glob.glob(os.path.join(target_dir, "*.csv"))):
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            if "pdb_id" not in reader.fieldnames:
                continue
            for row in reader:
                ids.append(row["pdb_id"].strip())
    # dedup preserve order
    seen = set()
    out = []
    for x in ids:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def synthetic_ids(count: int) -> List[str]:
    return [f"X{i+1}" for i in range(count)]


def to_af3_entry(name: str, seqs: List[dict]) -> dict:
    out = {
        "dialect": "alphafold3",
        "version": 2,
        "name": name,
        "sequences": [],
        "modelSeeds": SEEDS,
        "userCCD": None,
    }

    for seq in seqs:
        k = next(iter(seq))
        v = seq[k]

        if k == "proteinChain":
            count = int(v.get("count", 1))
            mods = []
            for m in v.get("modifications", []) or []:
                ptm = str(m.get("ptmType", ""))
                if ptm.startswith("CCD_"):
                    ptm = ptm[4:]
                mods.append({
                    "ptmType": ptm,
                    "ptmPosition": m.get("ptmPosition"),
                })
            out["sequences"].append({
                "protein": {
                    "id": synthetic_ids(count) if count > 1 else "X1",
                    "sequence": v.get("sequence", ""),
                    "modifications": mods,
                    "unpairedMsa": None,
                    "pairedMsa": None,
                    "templates": None,
                }
            })

        elif k == "rnaSequence":
            count = int(v.get("count", 1))
            mods = []
            for m in v.get("modifications", []) or []:
                mt = str(m.get("modificationType", ""))
                if mt.startswith("CCD_"):
                    mt = mt[4:]
                mods.append({
                    "modificationType": mt,
                    "basePosition": m.get("basePosition"),
                })
            out["sequences"].append({
                "rna": {
                    "id": synthetic_ids(count) if count > 1 else "X1",
                    "sequence": v.get("sequence", ""),
                    "modifications": mods,
                }
            })

        elif k == "dnaSequence":
            count = int(v.get("count", 1))
            mods = []
            for m in v.get("modifications", []) or []:
                mt = str(m.get("modificationType", ""))
                if mt.startswith("CCD_"):
                    mt = mt[4:]
                mods.append({
                    "modificationType": mt,
                    "basePosition": m.get("basePosition"),
                })
            out["sequences"].append({
                "dna": {
                    "id": synthetic_ids(count) if count > 1 else "X1",
                    "sequence": v.get("sequence", ""),
                    "modifications": mods,
                }
            })

        elif k == "ligand":
            count = int(v.get("count", 1))
            ligand = str(v.get("ligand", ""))
            ccd_codes = []
            if ligand.startswith("CCD_"):
                ccd_codes = [x for x in ligand.split("_")[1:] if x]
            out["sequences"].append({
                "ligand": {
                    "id": synthetic_ids(count) if count > 1 else "X1",
                    "ccdCodes": ccd_codes,
                }
            })

        else:
            raise ValueError(f"Unsupported sequence key: {k}")

    return out


def load_raw_entries(raw_dir: str) -> Dict[str, dict]:
    entries = {}
    for path in glob.glob(os.path.join(raw_dir, "*.json")):
        data = json.load(open(path))
        if not isinstance(data, list) or len(data) != 1:
            raise ValueError(f"Unexpected JSON shape in {path}")
        ent = data[0]
        name = ent.get("name") or os.path.basename(path).replace(".json", "")
        entries[name] = ent
    return entries


def write_manifest(entries: List[dict], out_path: str) -> Tuple[int, str]:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(entries, f, indent=2)
    h = hashlib.sha256(open(out_path, "rb").read()).hexdigest()
    return len(entries), h


def build_for_set(set_name: str, target_dir: str, raw_entries: Dict[str, dict], out_root: str):
    target_ids = load_target_ids(target_dir)
    missing = [x for x in target_ids if x not in raw_entries]
    af3 = []
    for tid in target_ids:
        if tid in raw_entries:
            af3.append(to_af3_entry(tid, raw_entries[tid].get("sequences", [])))

    out_dir = os.path.join(out_root, set_name)
    out_json = os.path.join(out_dir, "alphafold3_inputs.json")
    count, sha = write_manifest(af3, out_json)

    report = {
        "set": set_name,
        "target_dir": target_dir,
        "expected_targets": len(target_ids),
        "generated": count,
        "missing": len(missing),
        "missing_ids": missing[:50],
        "sha256": sha,
        "source_raw_dir": args.raw_json_dir,
    }
    with open(os.path.join(out_dir, "generation_report.json"), "w") as f:
        json.dump(report, f, indent=2)

    if missing:
        raise SystemExit(f"{set_name}: missing {len(missing)} targets (see generation_report.json)")


def main(args):
    raw_entries = load_raw_entries(args.raw_json_dir)
    build_for_set("full_2023plus", args.targets_dir, raw_entries, args.out_root)
    build_for_set("subset_2024plus", args.targets_2024_dir, raw_entries, args.out_root)
    print("done")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-json-dir", required=True)
    parser.add_argument("--targets-dir", required=True)
    parser.add_argument("--targets-2024-dir", required=True)
    parser.add_argument("--out-root", required=True)
    args = parser.parse_args()
    main(args)
