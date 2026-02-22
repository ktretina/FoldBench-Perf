#!/usr/bin/env python3
import json
from pathlib import Path
from datetime import datetime, timezone
import tempfile
import os


def utc_ts():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def atomic_write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + '.', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(obj, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def load_state(path: Path, default: dict):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def ensure_state(path: Path, af3_input_json: str, total_targets: int, expected_per_target: int):
    dflt = {
        'schema': 'foldbench.monolith.resume.v1',
        'created_at_utc': utc_ts(),
        'updated_at_utc': utc_ts(),
        'source_af3_input_json': str(Path(af3_input_json).resolve()),
        'total_targets': int(total_targets),
        'expected_per_target': int(expected_per_target),
        'targets': {},
        'segments': []
    }
    st = load_state(path, dflt)
    st.setdefault('targets', {})
    st.setdefault('segments', [])
    st['updated_at_utc'] = utc_ts()
    atomic_write_json(path, st)
    return st
