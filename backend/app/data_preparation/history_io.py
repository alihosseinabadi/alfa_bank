"""Immutable history snapshots and checksum-verified catalog linkage."""
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
import pandas as pd
from .chunking import digest
from .contracts import Material, Alias, ChildLink

def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+"\n",encoding="utf-8")

def write_jsonl(path: Path, rows) -> None:
    with path.open("w",encoding="utf-8") as stream:
        for row in rows:
            value=row.model_dump() if hasattr(row,"model_dump") else row
            stream.write(json.dumps(value,ensure_ascii=False,sort_keys=True,allow_nan=False)+"\n")

def read_jsonl(path: Path, model=None):
    return [model.model_validate_json(line) if model else json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

def resolve_bundle(path: Path) -> Path:
    if (path/"manifest.json").is_file():
        return path
    identity=(path/"CURRENT").read_text().strip()
    if not re.fullmatch("[a-f0-9]{64}",identity):
        raise ValueError("Invalid CURRENT pointer")
    return path/identity

def verify_files(directory: Path, manifest: dict) -> None:
    for name,entry in manifest["files"].items():
        filename=entry["filename"] if isinstance(entry,dict) else name
        if Path(filename).name!=filename:
            raise ValueError("Invalid artifact filename")
        expected=entry["sha256"] if isinstance(entry,dict) else entry
        if file_hash(directory/filename)!=expected:
            raise ValueError(f"Checksum mismatch: {filename}")

def load_source(path: Path):
    path=resolve_bundle(path)
    manifest=json.loads((path/"manifest.json").read_text())
    verify_files(path,manifest)
    if digest(manifest["files"])!=manifest["snapshot_id"]:
        raise ValueError("History snapshot identity mismatch")
    tables={}
    for name,entry in manifest["files"].items():
        frame=pd.read_csv(path/entry["filename"],dtype="string",keep_default_na=False)
        if list(frame.columns)!=entry["columns"] or len(frame)!=entry["rows"]:
            raise ValueError(f"Source schema/count mismatch: {name}")
        tables[name]=frame.to_dict("records")
    return tables,manifest

def load_catalog(path: Path):
    path=resolve_bundle(path)
    manifest=json.loads((path/"manifest.json").read_text())
    if manifest["config"]["catalog_version"]!="catalog-v2":
        raise ValueError("Incompatible catalog version")
    verify_files(path,manifest)
    materials=read_jsonl(path/"materials.jsonl",Material)
    aliases=read_jsonl(path/"aliases.jsonl",Alias)
    links=read_jsonl(path/"child_links.jsonl",ChildLink)
    return materials,aliases,links,manifest

def publish_bundle(output: Path, bundle_id: str, outputs: dict, metadata: dict) -> Path:
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".history-building-",dir=output) as directory:
        stage=Path(directory)
        for filename,rows in outputs.items():
            if filename.endswith(".jsonl"):
                write_jsonl(stage/filename,rows)
            else:
                write_json(stage/filename,rows)
        hashes={p.name:file_hash(p) for p in sorted(stage.iterdir())}
        manifest=dict(metadata,bundle_id=bundle_id,files=hashes)
        write_json(stage/"manifest.json",manifest)
        final=output/bundle_id
        if final.exists():
            existing=json.loads((final/"manifest.json").read_text())
            verify_files(final,existing)
            if existing["files"]!=hashes:
                raise ValueError("Immutable history bundle collision")
        else:
            os.replace(stage,final)
        pointer=output/"CURRENT.tmp"
        pointer.write_text(bundle_id+"\n",encoding="utf-8")
        os.replace(pointer,output/"CURRENT")
    return final
