"""Build and atomically publish a validated immutable stage-2 catalog bundle."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from collections import Counter
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.data_preparation.pipeline import build_catalog
from app.data_preparation.chunking import E5Tokenizer, chunk_blocks, digest
from app.data_preparation.contracts import CATALOG_VERSION, CLEANING_VERSION, ENCODER, ENCODER_REVISION
from app.data_preparation.eligibility import public_chunks
from app.data_preparation.url_checks import check_urls
from app.data_preparation.audit import audit_catalog

def write_jsonl(path, rows):
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row.model_dump() if hasattr(row,"model_dump") else row, ensure_ascii=False, sort_keys=True, allow_nan=False)+"\n")

def main():
    import tempfile
    parser=argparse.ArgumentParser()
    parser.add_argument("--input-dir",type=Path,default=ROOT/"data/interim")
    parser.add_argument("--output-dir",type=Path,default=ROOT/"data/processed/catalog")
    parser.add_argument("--tokenizer-dir",type=Path,default=ROOT/"artifacts/e5-tokenizer")
    parser.add_argument("--document-dir",type=Path)
    parser.add_argument("--check-urls",action="store_true")
    parser.add_argument("--url-timeout",type=float,default=5)
    parser.add_argument("--url-retries",type=int,default=1)
    parser.add_argument("--url-workers",type=int,default=4)
    parser.add_argument("--url-cache",type=Path)
    args=parser.parse_args()
    materials,aliases,blocks,links,source,extraction=build_catalog(args.input_dir,args.document_dir)
    print(f"Prepared {len(materials)} materials and {len(blocks)} text blocks",flush=True)
    urls=[]
    if args.url_cache:
        urls=[json.loads(line) for line in args.url_cache.read_text().splitlines() if line.strip()]
    if args.check_urls:
        urls=check_urls([m.url for m in materials if m.url and m.is_discoverable],
                       args.url_timeout,args.url_retries,args.url_workers)
    states={r["url"]:r["state"] for r in urls}
    for m in materials:
        m.url_state=states.get(m.url,"unchecked")
    print("URL states:",dict(Counter(m.url_state for m in materials)),flush=True)
    tokenizer=E5Tokenizer(args.tokenizer_dir)
    chunks=chunk_blocks(materials,blocks,tokenizer)
    public=public_chunks(materials,chunks)
    report=audit_catalog(materials,aliases,blocks,chunks,public,links,source)
    report["extraction"]=extraction
    try:
        commit=subprocess.check_output(["git","-C",str(ROOT),"rev-parse","HEAD"],text=True).strip()
        dirty=bool(subprocess.check_output(["git","-C",str(ROOT),"status","--porcelain"],text=True).strip())
    except subprocess.CalledProcessError:
        commit,dirty="unknown",True
    config={"catalog_version":CATALOG_VERSION,"cleaning_version":CLEANING_VERSION,"encoder":ENCODER,
            "encoder_revision":ENCODER_REVISION,"target_tokens":360,"max_tokens":512,"overlap_tokens":0,
            "route_version":"kurs-routes-v1","auxiliary_access_policy":"public_auxiliary_page_policy_v1"}
    # Build ID includes normalized content and runtime URL evidence, not wall-clock build time.
    code_inputs=list((ROOT/"backend/app/data_preparation").glob("*.py")) + list((ROOT/"scripts").glob("*catalog*.py"))
    code_fingerprint=digest({str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(code_inputs)})
    bundle_id=digest({"snapshot":source["snapshot_id"],"config":config,"code":code_fingerprint,
                      "materials":[m.model_dump() for m in materials],"chunks":[c.chunk_id for c in chunks],"urls":urls})
    args.output_dir.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".building-",dir=args.output_dir) as temp:
        stage=Path(temp)
        outputs={"materials.jsonl":materials,"aliases.jsonl":aliases,"content_blocks.jsonl":blocks,
                 "chunks.jsonl":chunks,"public_chunks.jsonl":public,
                 "entitled_chunks.jsonl":[c for c in chunks if c.access_scope=="entitled" and states.get(
                      next(m.url for m in materials if m.material_key==c.material_key))!="unavailable"],
                 "child_links.jsonl":links,"url_checks.jsonl":urls}
        for name,rows in outputs.items():
            write_jsonl(stage/name,rows)
        (stage/"audit.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        checksums={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in stage.iterdir() if p.is_file()}
        code_dir=ROOT/"backend/app/data_preparation"
        code_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in sorted(code_dir.glob("*.py"))}
        manifest={"bundle_id":bundle_id,"source_snapshot":source["snapshot_id"],"extracted_at":source["extracted_at"],
                  "config":config,"files":checksums,"code_commit":commit,"working_tree_dirty":dirty,
                  "code_sha256":code_hashes,"url_checks_run":bool(urls)}
        (stage/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
        final=args.output_dir/bundle_id
        if not final.exists():
            os.replace(stage,final)
        else:
            existing=json.loads((final/"manifest.json").read_text())
            if existing["files"]!=checksums:
                raise ValueError("Immutable bundle collision")
        pointer=args.output_dir/"CURRENT.tmp"
        pointer.write_text(bundle_id+"\n",encoding="utf-8")
        os.replace(pointer,args.output_dir/"CURRENT")
    print(json.dumps({k:report[k] for k in ["passed","materials","chunks","public_chunks","entitled_chunks","max_chunk_tokens"]},indent=2),flush=True)
    print("Bundle:",final,flush=True)

if __name__=="__main__":
    main()
