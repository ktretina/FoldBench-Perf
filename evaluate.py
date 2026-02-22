

from evaluation import eval_by_dockqv2,eval_by_ost
import pandas as pd
import argparse
import os
import sys



parser = argparse.ArgumentParser()
parser.add_argument(
    "--targets_dir", required=False, default='./examples/targets', help="The dir with the targets files."
)
parser.add_argument(
    "--evaluation_dir", required=False,default='./examples/outputs/evaluation', help="The dir with the evaluation files.",
)
parser.add_argument(
    "--algorithm_name", required=False, default='Protenix', help="The name of the algorithm.",
)
parser.add_argument(
    "--ground_truth_dir", required=False, default='./examples/ground_truths', help="The dir with the ground truth files.",
)

parser.add_argument(
        "--targets", required=False, default= ["interface_protein_ligand","interface_antibody_antigen","interface_protein_dna", "monomer_protein"], nargs='+', help="targets to evaluate.",
    )
args = parser.parse_args()

evaluation_dir = os.path.join(args.evaluation_dir,args.algorithm_name)

os.makedirs(os.path.join(evaluation_dir,'raw'), exist_ok=True)
target_types =  args.targets



prediction_summary_path = f'{evaluation_dir}/prediction_reference.csv'
if not os.path.exists(prediction_summary_path):
    print(f"ERROR: prediction reference file missing: {prediction_summary_path}")
    print("Hint: ensure inference postprocess generated prediction_reference.csv before running evaluate.py")
    sys.exit(6)

if os.path.getsize(prediction_summary_path) == 0:
    print(f"ERROR: prediction reference file is empty: {prediction_summary_path}")
    print("Hint: no predictions were indexed by postprocess; evaluation aborted fail-closed.")
    sys.exit(7)

try:
    prediction_summary_df = pd.read_csv(prediction_summary_path)
except pd.errors.EmptyDataError:
    print(f"ERROR: prediction reference has no parseable columns: {prediction_summary_path}")
    print("Hint: malformed/empty prediction_reference.csv; evaluation aborted fail-closed.")
    sys.exit(8)

if prediction_summary_df.empty:
    print(f"ERROR: prediction reference has 0 rows: {prediction_summary_path}")
    print("Hint: no predictions matched expected schema; evaluation aborted fail-closed.")
    sys.exit(9)

# caculation
for target_type in target_types:
    target_df_path = f'{args.targets_dir}/{target_type}.csv'
    if not os.path.exists(target_df_path):
        print(f"target_df_path is not exists for {target_type}")
        continue
    target_df = pd.read_csv(target_df_path)

    target_df = pd.merge(target_df,prediction_summary_df, on='pdb_id', how='left')

    if target_type in  ["interface_protein_protein","interface_antibody_antigen","interface_protein_peptide","interface_protein_ligand","interface_protein_dna","interface_protein_rna","monomer_dna","monomer_rna","monomer_protein"]:
        eval_by_ost(target_df,target_type,evaluation_dir,args.ground_truth_dir)
    
        if target_type in  ["interface_protein_dna","interface_protein_rna"]:
            eval_by_dockqv2(target_df,target_type,evaluation_dir,args.ground_truth_dir)