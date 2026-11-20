"""Evaluate the shipped demo retrieval against the frozen synthetic query set.

The catalogue is the same synthetic one the Docker stack builds, and the
retriever is the same BM25 + dense-vector hybrid the API serves.  The cases come
from ``data/synthetic/retrieval_cases_v2.json``: 100 hand-written business tasks,
including explicit empty and out-of-vocabulary cases.

This is a coverage/diagnostic evaluation, not a quality benchmark: the file has
no relevance judgments, so the script reports how many tasks retrieve anything
and which tasks do not.  It never claims conversion, sales or business impact.

Usage:
    python scripts/evaluate_demo_queries.py
    python scripts/evaluate_demo_queries.py --json reports/demo_query_eval.json
"""
import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

from app.data_preparation.retrieval_bundle import load_index  # noqa: E402
from app.ml.bm25_retriever import BM25Retriever  # noqa: E402
from app.ml.hybrid_retrieval import DenseHybridRetriever  # noqa: E402
from app.ml.lsa_retriever import LsaRetriever  # noqa: E402
from app.ml.profile_contracts import ExplicitConstraints, ExplicitPreferences  # noqa: E402
from app.ml.request_context import build_request_context  # noqa: E402
from app.ml.user_profile import build_user_profile  # noqa: E402
from build_demo_catalog import build  # noqa: E402

CASES = ROOT / "data/synthetic/retrieval_cases_v2.json"


def context_for(case: dict):
    profile = build_user_profile("synthetic:demo-query-eval", [], [], ExplicitPreferences())
    constraints = ExplicitConstraints(
        formats=list(case.get("formats") or []),
        budget_preference=case.get("budget_preference"),
    )
    return build_request_context(profile, case.get("task") or "", constraints)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=CASES)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="alfa-demo-eval-") as temp:
        base = Path(temp)
        build(base / "catalog", base / "retrieval", base / "embedding")
        index, _ = load_index(base / "retrieval")
        lexical = BM25Retriever().fit(list(index.materials.values()), index.rows)
        dense = LsaRetriever.load(base / "embedding")
        dense.attach_materials(index.materials.values())
        search = DenseHybridRetriever(dense, lexical, dense_weight=0.4)

        available_formats = {material.item_type for material in index.materials.values()}
        rows = []
        for case in cases:
            found = search.query(context_for(case), 3)
            requested = list(case.get("formats") or [])
            rows.append({
                "case_id": case["case_id"],
                "split": case["split"],
                "behavior": case.get("behavior"),
                "task": case.get("task") or "",
                "requested_formats": requested,
                "format_unavailable": bool(requested) and not (set(requested) & available_formats),
                "titles": [index.materials[key].title for key, _, _ in found],
                "material_keys": [key for key, _, _ in found],
            })

    normal = [row for row in rows if not row["behavior"] and row["task"].strip()]
    behavior = [row for row in rows if row["behavior"] or not row["task"].strip()]
    # A request for a format the demo catalogue does not contain (for example a
    # calculator) is an honest "not available", not a vocabulary failure.
    evaluable = [row for row in normal if not row["format_unavailable"]]
    matched = [row for row in evaluable if row["material_keys"]]
    behavior_passed = [row for row in behavior if not row["material_keys"]]

    summary = {
        "cases": len(rows),
        "normal_cases": len(normal),
        "format_unavailable_cases": [row["case_id"] for row in normal if row["format_unavailable"]],
        "evaluable_cases": len(evaluable),
        "evaluable_matched": len(matched),
        "evaluable_match_rate": round(len(matched) / len(evaluable), 4) if evaluable else 0,
        "behavior_cases": len(behavior),
        "behavior_passed": len(behavior_passed),
        "unmatched": [row["case_id"] for row in evaluable if not row["material_keys"]],
        "failed_behavior": [row["case_id"] for row in behavior if row["material_keys"]],
        "limitations": [
            "Synthetic hand-written tasks with no relevance judgments.",
            "Coverage of the 20-item synthetic demo catalogue, not production quality.",
            "Requests for formats absent from the catalogue are reported separately.",
            "No claim about conversion, sales, retention or business impact.",
        ],
    }

    for row in rows:
        if row["format_unavailable"]:
            mark = "FMT "
        else:
            mark = "MATCH" if row["material_keys"] else "  -- "
        print(f"{row['case_id']:<10} {row['split']:<5} {mark}  {row['task'][:70]}")
        if row["titles"]:
            print(f"{'':<10}             -> {row['titles'][0]}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps({"summary": summary, "per_case": rows},
                                        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if not summary["failed_behavior"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
