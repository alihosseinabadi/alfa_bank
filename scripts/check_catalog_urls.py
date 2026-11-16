"""Check supplied catalog URLs independently; save retryable observations."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from app.data_preparation.url_checks import check_urls

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--catalog-dir",type=Path,default=ROOT/"data/processed/catalog")
    parser.add_argument("--output",type=Path,default=ROOT/"data/interim/url_checks.jsonl")
    parser.add_argument("--timeout",type=float,default=5)
    parser.add_argument("--retries",type=int,default=1)
    parser.add_argument("--workers",type=int,default=4)
    args=parser.parse_args()
    directory=args.catalog_dir/(args.catalog_dir/"CURRENT").read_text().strip()
    materials=[json.loads(x) for x in (directory/"materials.jsonl").read_text().splitlines()]
    urls=[m["url"] for m in materials if m["is_discoverable"] and m["url"]]
    print(f"Checking {len(set(urls))} supplied material URLs",flush=True)
    results=check_urls(urls,args.timeout,args.retries,args.workers)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open("w",encoding="utf-8") as stream:
        for row in results:
            stream.write(json.dumps(row,ensure_ascii=False)+"\n")
    from collections import Counter
    print(dict(Counter(r["state"] for r in results)),flush=True)
    print(args.output,flush=True)

if __name__=="__main__":
    main()
