"""Run the public synthetic benchmark for every retrieval engine we ship.

Engines compared:

* ``tfidf``      - the production baseline (``tfidf-search-v1``)
* ``bm25``       - lexical BM25 over the shared tokenizer
* ``bm25_stem``  - experimental Snowball BM25
* ``char_ngram`` - char_wb TF-IDF channel on its own
* ``lsa``        - TruncatedSVD channel on its own
* ``light_hybrid`` - the new fused, versioned path

Metrics per (engine, split, family): NDCG@10, Success@5, pooled Recall@50,
refusal rate, and p50/p95 query latency with bootstrap 95% CIs.

Usage:
    python scripts/evaluate_light_retrieval.py
    python scripts/evaluate_light_retrieval.py --split dev --json out.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

from app.ml.bm25_retriever import BM25Retriever
from app.ml.bm25_ru_stem import RussianStemBM25Retriever
from app.ml.light_hybrid import LightHybridRetriever
from app.ml.lsa_retriever import LsaRetriever
from app.ml.ngram_retriever import CharNgramRetriever
from app.ml.retrieval_contracts import LIGHT_RETRIEVAL_VERSION, PublicSearchChunk, SearchMaterial
from app.ml.retrieval_metrics import judged_metrics
from app.ml.tfidf_retriever import TfidfRetriever
from make_light_benchmark import BENCHMARK_VERSION
from search_materials import context_for_case

BENCHMARK_DIR = ROOT / "data" / "synthetic" / "light_benchmark_v1"
# Engine -> score compared against; NDCG needs graded relevance, not raw scores.
ENGINE_NAMES = ["tfidf", "bm25", "bm25_stem", "char_ngram", "lsa", "light_hybrid"]

RELEVANCE_FAMILIES = ("natural", "paraphrase")
TOP_K = 50
BOOTSTRAP_ROUNDS = 2000
BOOTSTRAP_SEED = 7

# Left engine minus right engine. These are the claims the report makes.
PAIRWISE = [
    ("light_hybrid", "bm25"),
    ("light_hybrid", "tfidf"),
    ("light_hybrid", "bm25_stem"),
    ("light_hybrid", "char_ngram"),
    ("light_hybrid", "lsa"),
    ("bm25_stem", "bm25"),
]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_benchmark(directory: Path = BENCHMARK_DIR) -> tuple[list, list, dict, dict]:
    catalog = json.loads((directory / "catalog.json").read_text(encoding="utf-8"))
    queries = json.loads((directory / "queries.json").read_text(encoding="utf-8"))
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if catalog["version"] != BENCHMARK_VERSION or queries["version"] != BENCHMARK_VERSION:
        raise ValueError("Benchmark version mismatch")
    materials = [SearchMaterial(**row) for row in catalog["materials"]]
    chunks = [PublicSearchChunk(**row) for row in catalog["chunks"]]
    return materials, chunks, queries, manifest


# ---------------------------------------------------------------------------
# Engine adapters: every engine exposes (keys, matched) for a context
# ---------------------------------------------------------------------------

def _single_channel(query_fn: Callable[[Any, int], list]) -> Callable[[Any, int], tuple[list, bool]]:
    def run(context: Any, k: int) -> tuple[list, bool]:
        rows = query_fn(context, k)
        return [row[0] for row in rows], bool(rows)
    return run


def build_engines(materials, chunks) -> dict[str, Callable[[Any, int], tuple[list, bool]]]:
    engines: dict[str, Callable[[Any, int], tuple[list, bool]]] = {}

    tfidf = TfidfRetriever().fit(materials, chunks)

    def run_tfidf(context: Any, k: int) -> tuple[list, bool]:
        result = tfidf.query(context, k)
        return [row.material_key for row in result.candidates], result.status == "matched"

    engines["tfidf"] = run_tfidf

    bm25 = BM25Retriever().fit(materials, chunks)
    engines["bm25"] = _single_channel(bm25.query)

    bm25_stem = RussianStemBM25Retriever().fit(materials, chunks)
    engines["bm25_stem"] = _single_channel(bm25_stem.query)

    char_ngram = CharNgramRetriever().fit(materials, chunks)
    engines["char_ngram"] = _single_channel(char_ngram.query)

    lsa = LsaRetriever().fit(materials, chunks)
    engines["lsa"] = _single_channel(lsa.query)

    hybrid = LightHybridRetriever().fit(materials, chunks)
    if hybrid.identity is None:
        raise ValueError("Light hybrid was not fitted")

    def run_hybrid(context: Any, k: int) -> tuple[list, bool]:
        result = hybrid.query(context, k)
        return [row.material_key for row in result.candidates], result.status == "matched"

    engines["light_hybrid"] = run_hybrid
    return engines


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def bootstrap_ci(values: list[float], rounds: int = BOOTSTRAP_ROUNDS,
                 seed: int = BOOTSTRAP_SEED) -> tuple[float, float, float]:
    """Mean and 95% percentile bootstrap CI over independent cases."""
    if not values:
        return 0.0, 0.0, 0.0
    array = np.asarray(values, dtype=np.float64)
    mean = float(array.mean())
    if len(array) == 1:
        return mean, mean, mean
    rng = np.random.default_rng(seed)
    draws = rng.choice(array, size=(rounds, len(array)), replace=True).mean(axis=1)
    low, high = np.percentile(draws, [2.5, 97.5])
    return mean, float(low), float(high)


def _metric_block(values: list[float]) -> dict[str, Any]:
    mean, low, high = bootstrap_ci(values)
    return {"mean": round(mean, 4), "ci95": [round(low, 4), round(high, 4)], "n": len(values)}


def evaluate_engines(engines, cases: list[dict[str, Any]], split: str | None) -> dict[str, Any]:
    selected = [case for case in cases if split is None or case["split"] == split]
    report: dict[str, Any] = {"cases": len(selected), "engines": {}, "per_case": {}}

    for name in ENGINE_NAMES:
        run = engines[name]
        # Warm-up pass, then the timed pass. Results are deterministic.
        for case in selected:
            run(context_for_case(case), TOP_K)

        per_family: dict[str, dict[str, list[float]]] = {}
        per_case: dict[str, dict[str, float]] = {}
        refusals: list[float] = []
        latencies: list[float] = []
        constraint_violations = 0
        constraint_cases = 0
        constraint_with_results = 0

        for case in selected:
            context = context_for_case(case)
            start = time.perf_counter()
            keys, matched = run(context, TOP_K)
            latencies.append((time.perf_counter() - start) * 1000)

            if case["intent"] == "refusal":
                refusals.append(0.0 if matched and keys else 1.0)
                continue
            if case["intent"] == "constraint":
                constraint_cases += 1
                constraint_with_results += 1 if keys else 0
                constraint_violations += _constraint_violations(keys, case)
                continue

            metrics = judged_metrics(keys, case["grades"], k=10)
            normalised = {
                "ndcg10": metrics["ndcg10"],
                "success5": metrics["success5"],
                "recall50": metrics["pooled_recall50"],
                "refused": 0.0 if matched else 1.0,
            }
            bucket = per_family.setdefault(
                case["family"], {"ndcg10": [], "success5": [], "recall50": [], "refused": []}
            )
            for metric, value in normalised.items():
                bucket[metric].append(value)
            per_case[case["case_id"]] = normalised

        families = {
            family: {metric: _metric_block(values[metric]) for metric in values}
            for family, values in sorted(per_family.items())
        }
        metrics_of_interest = ("ndcg10", "success5", "recall50")
        combined = {
            metric: _metric_block([value for bucket in per_family.values() for value in bucket[metric]])
            for metric in metrics_of_interest
        }
        report["engines"][name] = {
            "families": families,
            "relevance_all": combined,
            "refusal": _metric_block(refusals) if refusals else None,
            "latency_ms": _latency_block(latencies),
            "constraints": {
                "cases": constraint_cases,
                "violations": constraint_violations,
                "cases_with_results": constraint_with_results,
            },
        }
        report["per_case"][name] = per_case
    return report


def paired_comparisons(report: dict[str, Any], pairs: list[tuple[str, str]]) -> dict[str, Any]:
    """Paired bootstrap on the per-case difference ``pairs[i][0] - pairs[i][1]``.

    Marginal CIs overlap easily on small case counts; a paired difference over the
    same cases is the right test for "engine A is not worse than engine B".
    """
    output: dict[str, Any] = {}
    for left, right in pairs:
        left_cases = report["per_case"][left]
        right_cases = report["per_case"][right]
        shared = sorted(set(left_cases) & set(right_cases))
        block: dict[str, Any] = {"cases": len(shared), "metrics": {}}
        for metric in ("ndcg10", "success5"):
            deltas = [left_cases[key][metric] - right_cases[key][metric] for key in shared]
            mean, low, high = bootstrap_ci(deltas)
            block["metrics"][metric] = {
                "delta": round(mean, 4),
                "ci95": [round(low, 4), round(high, 4)],
                "wins": sum(1 for delta in deltas if delta > 1e-9),
                "losses": sum(1 for delta in deltas if delta < -1e-9),
                "ties": sum(1 for delta in deltas if abs(delta) <= 1e-9),
            }
        output[f"{left}_minus_{right}"] = block
    return output


def _constraint_violations(keys: list[str], case: dict[str, Any]) -> int:
    """Count returned materials that break the case constraint (must be zero)."""
    by_key = _MATERIALS_BY_KEY
    violations = 0
    for key in keys:
        material = by_key.get(key)
        if material is None:
            continue
        if case.get("budget_preference") == "free_only" and material.access_type != "Открытый":
            violations += 1
        formats = case.get("formats")
        if formats and material.item_type not in formats:
            violations += 1
        limit = case.get("available_time_minutes")
        if limit is not None and material.duration_minutes is not None and material.duration_minutes > limit:
            violations += 1
    return violations


def _latency_block(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"p50": 0.0, "p95": 0.0, "n": 0}
    ordered = sorted(values)
    return {
        "p50": round(statistics.median(ordered), 2),
        "p95": round(float(np.percentile(ordered, 95)), 2),
        "mean": round(statistics.fmean(ordered), 2),
        "n": len(ordered),
    }


# ---------------------------------------------------------------------------
# Presentation
# ---------------------------------------------------------------------------

def markdown_report(report: dict[str, Any], comparisons: dict[str, Any]) -> str:
    lines: list[str] = []
    header = (
        "| engine | family | NDCG@10 (95% CI) | Success@5 (95% CI) | Recall@50 "
        "| refused| p50 ms | p95 ms |"
    )
    divider = "|---|---|---|---|---|---|---|---|"
    for split, payload in report.items():
        lines.append(f"\n#### {split} ({payload['cases']} cases)\n")
        lines.append(header)
        lines.append(divider)
        for name in ENGINE_NAMES:
            engine = payload["engines"][name]
            latency = engine["latency_ms"]
            for family, block in engine["families"].items():
                lines.append(
                    "| {engine} | {family} | {ndcg} | {succ} | {recall} | {refused} | {p50} | {p95} |".format(
                        engine=name, family=family,
                        ndcg=_fmt(block["ndcg10"]), succ=_fmt(block["success5"]),
                        recall=_fmt(block["recall50"], ci=False),
                        refused=_fmt(block["refused"], ci=False),
                        p50=latency["p50"], p95=latency["p95"],
                    )
                )
            refusal = engine["refusal"]
            if refusal:
                lines.append(
                    f"| {name} | refusal(off-topic) | {_fmt(refusal, metric_only=True)} | - | - | - "
                    f"| {latency['p50']} | {latency['p95']} |"
                )
        lines.append("\nPaired differences over the same cases (positive = left engine better):\n")
        lines.append("| comparison | cases | NDCG@10 delta (95% CI) | wins/losses/ties | Success@5 delta (95% CI) | wins/losses/ties |")
        lines.append("|---|---|---|---|---|---|")
        for name, block in comparisons[split].items():
            ndcg = block["metrics"]["ndcg10"]
            succ = block["metrics"]["success5"]
            lines.append(
                f"| {name} | {block['cases']} | {ndcg['delta']:+.3f} "
                f"[{ndcg['ci95'][0]:+.3f}, {ndcg['ci95'][1]:+.3f}] "
                f"| {ndcg['wins']}/{ndcg['losses']}/{ndcg['ties']} "
                f"| {succ['delta']:+.3f} [{succ['ci95'][0]:+.3f}, {succ['ci95'][1]:+.3f}] "
                f"| {succ['wins']}/{succ['losses']}/{succ['ties']} |"
            )
    return "\n".join(lines)


def _fmt(block: dict[str, Any], *, ci: bool = True, metric_only: bool = False) -> str:
    if metric_only:
        return f"{block['mean']:.3f}"
    text = f"{block['mean']:.3f}"
    if ci:
        text += f" [{block['ci95'][0]:.3f}, {block['ci95'][1]:.3f}]"
    return text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark-dir", type=Path, default=BENCHMARK_DIR)
    parser.add_argument("--split", choices=["dev", "holdout", "all"], default="all")
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    materials, chunks, queries, manifest = load_benchmark(args.benchmark_dir)
    global _MATERIALS_BY_KEY
    _MATERIALS_BY_KEY = {material.material_key: material for material in materials}
    engines = build_engines(materials, chunks)

    splits = ["dev", "holdout"] if args.split == "all" else [None if args.split == "all" else args.split]
    report: dict[str, Any] = {}
    comparisons: dict[str, Any] = {}
    for split in splits:
        label = split or "all"
        report[label] = evaluate_engines(engines, queries["cases"], split)
        comparisons[label] = paired_comparisons(report[label], PAIRWISE)

    payload = {
        "benchmark": {
            "version": manifest["version"],
            "catalog_hash": manifest["files"]["catalog.json"],
            "queries_hash": manifest["files"]["queries.json"],
            "holdout_hash": manifest["holdout_hash"],
            "summary": manifest["summary"],
            "cases_by_split": manifest["cases_by_split"],
        },
        "retrieval_version": LIGHT_RETRIEVAL_VERSION,
        "metrics": {
            label: {
                "cases": block["cases"],
                "engines": block["engines"],
            }
            for label, block in report.items()
        },
        "paired": comparisons,
    }
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        print(f"wrote {args.json}")
    print(markdown_report(report, comparisons))


_MATERIALS_BY_KEY: dict[str, SearchMaterial] = {}

if __name__ == "__main__":
    main()
