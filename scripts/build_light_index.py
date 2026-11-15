"""Build or verify the local light (stemmed hybrid) retrieval index.

Usage:
    python scripts/build_light_index.py
    python scripts/build_light_index.py --verify
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.data_preparation.light_index import build_light_index, load_light_index, save_light_index
from app.data_preparation.retrieval_bundle import catalog_search_inputs
from app.ml.retrieval_contracts import LightRetrievalPolicy


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog-dir", type=Path, default=ROOT / "data/processed/catalog")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts/light")
    parser.add_argument("--lsa-components", type=int, default=120)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        index, manifest = load_light_index(args.output_dir)
        print(json.dumps({"verified": True, "bundle_id": manifest["bundle_id"],
                          "audit": manifest["audit"]}, ensure_ascii=False, indent=2))
        return
    materials, chunks, catalog = catalog_search_inputs(args.catalog_dir)
    policy = LightRetrievalPolicy(lsa_components=args.lsa_components)
    index = build_light_index(materials, chunks, policy)
    path = save_light_index(index, args.output_dir, ROOT,
                            catalog_bundle_id=catalog["bundle_id"],
                            catalog_files=catalog["files"])
    print(json.dumps({"bundle": str(path), "identity": index.identity,
                      "audit": {"materials": len(index.materials), "chunks": len(index.rows),
                                "lsa_components": index.lsa.components}},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
