"""Build normalized observations and continuation state from local exports."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from app.data_preparation.history_bundle import build_history

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--source-dir",type=Path,default=ROOT/"data/interim/history")
    parser.add_argument("--catalog-dir",type=Path,default=ROOT/"data/processed/catalog")
    parser.add_argument("--output-dir",type=Path,default=ROOT/"data/processed/history")
    parser.add_argument("--cutoff-month",help="Optional global YYYY-MM boundary; no within-month ordering")
    args=parser.parse_args()
    path,report=build_history(args.source_dir,args.catalog_dir,args.output_dir,ROOT,args.cutoff_month)
    print(json.dumps({key:report[key] for key in ("passed","accepted","unassigned","rejected","evaluation_inputs","states_with_candidates")},indent=2))
    print("History bundle:",path)

if __name__=="__main__":
    main()
