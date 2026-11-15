"""Verify an existing catalog bundle before a downstream index build."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from app.data_preparation.contracts import Material,Alias,ContentBlock,Chunk,ChildLink
from app.data_preparation.chunking import E5Tokenizer
from app.data_preparation.audit import audit_catalog
from app.data_preparation.pipeline import load_manifest

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--catalog-dir",type=Path,default=ROOT/"data/processed/catalog")
    parser.add_argument("--source-dir",type=Path,default=ROOT/"data/interim")
    parser.add_argument("--tokenizer-dir",type=Path,default=ROOT/"artifacts/e5-tokenizer")
    args=parser.parse_args()
    bundle=args.catalog_dir/(args.catalog_dir/"CURRENT").read_text().strip()
    manifest=json.loads((bundle/"manifest.json").read_text())
    for name,expected in manifest["files"].items():
        if hashlib.sha256((bundle/name).read_bytes()).hexdigest()!=expected:
            raise ValueError(f"Corrupted artifact: {name}")
    def read(name,model):
        return [model.model_validate_json(line) for line in (bundle/name).read_text().splitlines() if line]
    materials=read("materials.jsonl",Material)
    aliases=read("aliases.jsonl",Alias)
    blocks=read("content_blocks.jsonl",ContentBlock)
    chunks=read("chunks.jsonl",Chunk)
    public=read("public_chunks.jsonl",Chunk)
    links=read("child_links.jsonl",ChildLink)
    report=audit_catalog(materials,aliases,blocks,chunks,public,links,load_manifest(args.source_dir))
    tokenizer=E5Tokenizer(args.tokenizer_dir)
    for c in chunks:
        if tokenizer.count(c.text)!=c.token_count:
            raise ValueError("Chunk token count mismatch")
    print(json.dumps({"bundle_id":manifest["bundle_id"],"passed":report["passed"],
                     "materials":report["materials"],"chunks":report["chunks"]},indent=2))

if __name__=="__main__":
    main()
