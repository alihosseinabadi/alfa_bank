"""Independently re-read and validate a published history artifact bundle."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from app.data_preparation.history_bundle import verify_history

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--history-dir",type=Path,default=ROOT/"data/processed/history")
    parser.add_argument("--source-dir",type=Path,default=ROOT/"data/interim/history")
    parser.add_argument("--catalog-dir",type=Path,default=ROOT/"data/processed/catalog")
    args=parser.parse_args()
    manifest,report=verify_history(args.history_dir,args.source_dir,args.catalog_dir)
    print(json.dumps({"bundle_id":manifest["bundle_id"],"passed":report["passed"],
                      "source_reconciliation":report["source_reconciliation"]},indent=2))

if __name__=="__main__":
    main()
