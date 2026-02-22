#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/ktretina/.openclaw/workspace/github_projects/FoldBench"
ALGO_DIR="$ROOT/algorithms/Protenix"
DEF_FILE="$ALGO_DIR/container.def"
SIF_OUT="$ALGO_DIR/container.sif"
SANDBOX="${ALGO_DIR}/container.sandbox"
BUILD_CTX="${ROOT}/.build_ctx_protenix"

if [[ ! -f "$DEF_FILE" ]]; then
  echo "ERROR: missing $DEF_FILE" >&2
  exit 1
fi

FROM_IMAGE=$(awk '/^From:/{print $2; exit}' "$DEF_FILE")
if [[ -z "${FROM_IMAGE:-}" ]]; then
  echo "ERROR: unable to parse base image From: from $DEF_FILE" >&2
  exit 1
fi

echo "[1/6] Base image: $FROM_IMAGE"

rm -rf "$SANDBOX" "$BUILD_CTX"
mkdir -p "$BUILD_CTX"

# Build userns sandbox from docker base (works without sudo/newuidmap for docker:// sources)
echo "[2/6] Building sandbox from docker base"
apptainer build --userns --sandbox "$SANDBOX" "docker://${FROM_IMAGE}"

# Stage algorithm files into build context and bind-mount as /algo
echo "[3/6] Staging algorithm files"
cp -a "$ALGO_DIR" "$BUILD_CTX/algo"

# Install Protenix inside sandbox and ensure runner script executable
echo "[4/6] Installing Protenix inside sandbox (/algo/Protenix)"
apptainer exec --userns --writable \
  --bind "$BUILD_CTX/algo:/tmp/algo_src" \
  "$SANDBOX" \
  bash -lc 'set -euo pipefail; \
    mkdir -p /algo; cp -a /tmp/algo_src/. /algo/; \
    /opt/conda/bin/python -V; \
    apt-get update && apt-get install -y --no-install-recommends git g++ gcc libc6-dev make hmmer kalign && apt-get clean && rm -rf /var/lib/apt/lists/*; \
    git clone -b v3.5.1 https://github.com/NVIDIA/cutlass.git /opt/cutlass || true; \
    cd /algo/Protenix; /opt/conda/bin/pip install -e .; \
    chmod +x /algo/make_predictions.sh'

# Pack sandbox into sif
if [[ -f "$SIF_OUT" ]]; then
  rm -f "$SIF_OUT"
fi

echo "[5/6] Packing sandbox -> $SIF_OUT"
apptainer build --userns "$SIF_OUT" "$SANDBOX"

# Cleanup build scratch
rm -rf "$BUILD_CTX"

echo "[6/6] Done"
ls -lh "$SIF_OUT"
