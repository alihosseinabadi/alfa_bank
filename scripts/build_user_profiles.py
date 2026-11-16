"""Build current or historical MVP profiles from checksum-verified local inputs."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from app.data_preparation.profile_bundle import build_profiles
from app.ml.profile_contracts import ExplicitPreferences
from app.ml.profile_policy import ProfilePolicy

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--history-dir",type=Path,default=ROOT/"data/processed/history")
    parser.add_argument("--catalog-dir",type=Path,default=ROOT/"data/processed/catalog")
    parser.add_argument("--source-dir",type=Path,default=ROOT/"data/interim/history")
    parser.add_argument("--output-dir",type=Path,default=ROOT/"data/processed/profiles")
    parser.add_argument("--cutoff-month")
    parser.add_argument("--policy",type=Path)
    parser.add_argument("--explicit-preferences",type=Path,help="Private JSON mapping user_key to supplied preferences")
    args=parser.parse_args()
    policy=ProfilePolicy.model_validate_json(args.policy.read_text()) if args.policy else None
    explicit={key:ExplicitPreferences.model_validate(value) for key,value in json.loads(args.explicit_preferences.read_text()).items()} if args.explicit_preferences else {}
    output,audit=build_profiles(args.history_dir,args.catalog_dir,args.source_dir,args.output_dir,ROOT,
        cutoff_month=args.cutoff_month,policy=policy,explicit=explicit)
    print(json.dumps({key:audit[key] for key in ("passed","profiles","profiles_with_topics","profiles_with_negative_evidence","cold_start_profiles")},indent=2))
    print("Profile bundle:",output)

if __name__=="__main__":main()
