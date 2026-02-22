# bash run.sh Protenix 1

#!/bin/bash
algorithm="$1"
gpu_id="$2"

af3_input_json=./examples/alphafold3_inputs.json 
targets_dir=./examples/targets
output_root_dir="./examples/outputs"
time_log_root_dir="./examples/times"
ground_truth_dir="./examples/ground_truths"
overlay_size=2048


prediction_root_dir="$output_root_dir/prediction"
evaluation_root_dir="$output_root_dir/evaluation"
input_root_dir="$output_root_dir/input"
time_log_dir="$time_log_root_dir"

recalculate=false

while getopts ":r" opt; do
  case $opt in
    r) recalculate=true
    ;;
    \?) echo "Invalid option -$OPTARG" >&2
    ;;
  esac
done
echo "Recalculate all algorithm outputs: $recalculate"

if "$recalculate"; then
    # Clean output dir 
    rm -rf "$prediction_root_dir"
    rm -rf "$evaluation_root_dir"
    rm -rf "$input_root_dir"
    rm -rf "$time_log_dir"
fi

# Create the output directory if it doesn't exist
mkdir -p "$prediction_root_dir"
mkdir -p "$evaluation_root_dir"
mkdir -p "$input_root_dir"
mkdir -p "$time_log_dir"

# start evaluation environment
conda init
. /root/miniconda3/etc/profile.d/conda.sh
conda activate foldbench

# Hard gate: true GPU path required
GPU_CHECK_TARGET="algorithms/Protenix/container.sandbox"
if [ ! -d "$GPU_CHECK_TARGET" ]; then
    GPU_CHECK_TARGET="algorithms/Protenix/container.sif"
fi
if ! apptainer exec --nvccli "$GPU_CHECK_TARGET" nvidia-smi -L >/dev/null 2>&1; then
    echo "ERROR: true GPU path check failed (apptainer --nvccli nvidia-smi -L). Aborting." >&2
    exit 3
fi

# Loop through each algorithm in the algorithms directory
for algorithm_dir in algorithms/*; do

    if [ -d "$algorithm_dir" ] && [ $(basename "$algorithm_dir") != "base" ]; then
        algorithm_name=$(basename "$algorithm_dir")

        # If an algorithm is specified, only continue if algorithm_name matches
        if [ -z "$algorithm" ] || [ "$algorithm_name" == "$algorithm" ]; then

            prediction_dir="$prediction_root_dir/${algorithm_name}"
            time_log_file="$time_log_dir/${algorithm_name}_time.log"
            # Check if the output file does not exist
            # if [ ! -e "$prediction_dir" ]; then
            if [ -e "$prediction_dir" ]; then
                echo "Processing algorithm: $algorithm_name"

                input_dir="$input_root_dir/${algorithm_name}"
                evaluation_dir="$evaluation_root_dir/${algorithm_name}"
                
                # create dirs for prediction, input, evaluation
                mkdir -p "$prediction_dir"
                mkdir -p "$input_dir"
                mkdir -p "$evaluation_dir"

                # No overlay image: EXT3 overlay mounts require loop device access
                # that is not available on this host for unprivileged runs.

                # Calculate predictions
                echo "RUN ALGORITHM $algorithm_name"
                { time ( apptainer exec --userns --nvccli \
                    -B $af3_input_json:/algo/alphafold3_inputs.json \
                    -B $output_root_dir:/algo/outputs \
                    "algorithms/${algorithm_name}/container.sif" \
                    bash -c "cd /algo \
                    && ./make_predictions.sh ${af3_input_json} ${input_dir} ${prediction_dir} ${evaluation_dir} ${gpu_id}" 2>&1 ); } 2> "$time_log_file"
                
                echo "EVALUATE PREDICTIONS"
                python evaluate.py --targets_dir ${targets_dir} --prediction_dir ${prediction_dir} --evaluation_dir ${evaluation_dir} --ground_truth_dir ${ground_truth_dir}
                python task_score_summary.py --algorithm_names ${algorithm_name}
                
            else
                echo "Skipping algorithm: $algorithm_name. Output file already exists."

                # No overlay cleanup needed in no-overlay runtime mode.
            fi

        fi

    fi
done