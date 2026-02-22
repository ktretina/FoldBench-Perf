#!/usr/bin/env python3
import argparse, csv, glob, json
from pathlib import Path


def load_ids(target_dir):
    ids=[]
    for p in sorted(glob.glob(str(Path(target_dir)/'*.csv'))):
        with open(p) as f:
            r=csv.DictReader(f)
            if 'pdb_id' not in (r.fieldnames or []):
                continue
            for row in r:
                x=(row.get('pdb_id') or '').strip()
                if x: ids.append(x)
    seen=set(); out=[]
    for x in ids:
        if x not in seen:
            seen.add(x); out.append(x)
    return out


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--target-dir', required=True)
    ap.add_argument('--size', type=int, default=100)
    ap.add_argument('--out-dir', required=True)
    args=ap.parse_args()

    ids=load_ids(args.target_dir)
    out=Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    shards=[]
    for i in range(0,len(ids),args.size):
        sid=f'shard_{i//args.size+1:03d}'
        chunk=ids[i:i+args.size]
        p=out/f'{sid}.json'
        p.write_text(json.dumps({'shard_id':sid,'size':len(chunk),'targets':chunk},indent=2))
        shards.append({'shard_id':sid,'size':len(chunk),'path':str(p)})

    (out/'manifest.json').write_text(json.dumps({'target_dir':args.target_dir,'total_targets':len(ids),'shard_size':args.size,'shards':shards},indent=2))
    print(str(out/'manifest.json'))

if __name__=='__main__':
    main()
