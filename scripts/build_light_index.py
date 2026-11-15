"""Build or verify the local light (stemmed hybrid) retrieval index.

Usage:
    python scripts/build_light_index.py                 # v1 (default, unchanged)
    python scripts/build_light_index.py --version v2    # material-level semantic channel
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
from app.ml.retrieval_contracts import LightRetrievalPolicy, LightRetrievalPolicyV2


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog-dir", type=Path, default=ROOT / "data/processed/catalog")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "artifacts/light")
    parser.add_argument("--version", choices=("v1", "v2"), default="v1")
    parser.add_argument("--lsa-components", type=int, default=None,
                        help="v1: chunk LSA components (120); v2: semantic components (40)")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        index, manifest = load_light_index(args.output_dir)
        print(json.dumps({"verified": True, "bundle_id": manifest["bundle_id"],
                          "audit": manifest["audit"]}, ensure_ascii=False, indent=2))
        return
    materials, chunks, catalog = catalog_search_inputs(args.catalog_dir)
    if args.version == "v2":
        policy = LightRetrievalPolicyV2(
            semantic_components=args.lsa_components or LightRetrievalPolicyV2().semantic_components
        )
    else:
        policy = LightRetrievalPolicy(
            lsa_components=args.lsa_components or LightRetrievalPolicy().lsa_components
        )
    index = build_light_index(materials, chunks, policy)
    path = save_light_index(index, args.output_dir, ROOT,
                            catalog_bundle_id=catalog["bundle_id"],
                            catalog_files=catalog["files"])
    components = getattr(getattr(index, "lsa", None), "components", None)
    if components is None:
        components = getattr(getattr(index, "semantic", None), "components", 0)
    print(json.dumps({"bundle": str(path), "identity": index.identity,
                      "version": index.retrieval_version,
                      "audit": {"materials": len(index.materials), "chunks": len(index.rows),
                                "components": components}},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
