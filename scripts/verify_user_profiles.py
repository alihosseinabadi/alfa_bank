"""Reconstruct profiles and validate provenance, versions and saved checksums."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from app.data_preparation.profile_bundle import verify_profiles

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--profiles-dir",type=Path,default=ROOT/"data/processed/profiles")
    parser.add_argument("--history-dir",type=Path,default=ROOT/"data/processed/history")
    parser.add_argument("--catalog-dir",type=Path,default=ROOT/"data/processed/catalog")
    parser.add_argument("--source-dir",type=Path,default=ROOT/"data/interim/history")
    args=parser.parse_args()
    manifest,audit=verify_profiles(args.profiles_dir,args.history_dir,args.catalog_dir,args.source_dir)
    print(json.dumps({"bundle_id":manifest["bundle_id"],"passed":audit["passed"],"profiles":audit["profiles"]},indent=2))

if __name__=="__main__":main()
