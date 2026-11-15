"""Build or fully verify the local public retrieval index."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from app.data_preparation.retrieval_bundle import build_index,verify_index
from app.ml.retrieval_contracts import RetrievalPolicy

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--catalog-dir",type=Path,default=ROOT/"data/processed/catalog")
    parser.add_argument("--output-dir",type=Path,default=ROOT/"artifacts/retrieval")
    parser.add_argument("--min-similarity",type=float,default=.04)
    parser.add_argument("--verify",action="store_true")
    args=parser.parse_args()
    if args.verify:
        manifest,audit=verify_index(args.output_dir,args.catalog_dir)
        print(json.dumps({"verified":True,"bundle_id":manifest["bundle_id"],"audit":audit},ensure_ascii=False,indent=2))
    else:
        path,audit=build_index(args.catalog_dir,args.output_dir,ROOT,RetrievalPolicy(min_similarity=args.min_similarity))
        print(json.dumps({"bundle":str(path),"audit":audit},ensure_ascii=False,indent=2))
if __name__=="__main__":main()
