#!/bin/bash
set -euo pipefail

build_one() {
  local force_flag="$1"
  local container_sif="$2"
  local container_def="$3"
  local algo_name="$4"

  local cmd=(apptainer build --userns)
  if [[ "$force_flag" == "force" ]]; then
    cmd+=(--force)
  fi
  cmd+=("$container_sif" "$container_def")

  echo "[build] ${algo_name}: local build"
  if "${cmd[@]}"; then
    return 0
  fi

  echo "[warn] ${algo_name}: --userns build failed; retrying plain local build"
  local retry_cmd=(apptainer build)
  if [[ "$force_flag" == "force" ]]; then
    retry_cmd+=(--force)
  fi
  retry_cmd+=("$container_sif" "$container_def")
  "${retry_cmd[@]}"
}

# --- Function to build Apptainer images ---
build_apptainer_image() {
  container_sif="$1"
  container_def="$2"
  algo_name="$3"

  if [ -f "$container_sif" ]; then
    read -p "A .sif image for $algo_name already exists. Force rebuild? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
      build_one force "$container_sif" "$container_def" "$algo_name"
    else
      echo "Skipping rebuild for $algo_name image."
    fi
  else
    echo "Building $algo_name image..."
    build_one noforce "$container_sif" "$container_def" "$algo_name"
  fi
}

# --- Build algorithm images ---
# Loop through each directory (algorithm) in the "algorithms" folder
for algo_name in algorithms/*; do
  # echo "Building $algo_name image..."
  # Check if it's a directory and not the "base" folder
  if [ -d "$algo_name" ] && [ "${algo_name##*/}" != "base" ]; then 
    # Construct the full paths for the command
    container_sif="algorithms/${algo_name##*/}/container.sif"
    container_def="algorithms/${algo_name##*/}/container.def"
    
    # Build the algorithm image
    build_apptainer_image "$container_sif" "$container_def" "${algo_name##*/}"
  fi
done