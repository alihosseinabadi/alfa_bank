"""Explicitly download only the pinned E5 tokenizer, never model weights."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.data_preparation.contracts import ENCODER, ENCODER_REVISION

def main():
    from huggingface_hub import hf_hub_download
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts/e5-tokenizer")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    path = Path(hf_hub_download(ENCODER, "tokenizer.json", revision=ENCODER_REVISION, local_dir=args.output_dir))
    manifest = {"model": ENCODER, "revision": ENCODER_REVISION,
                "files": {"tokenizer.json": hashlib.sha256(path.read_bytes()).hexdigest()}}
    (args.output_dir / "catalog_tokenizer.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))

if __name__ == "__main__":
    main()
