"""Measure LinUCB scoring latency: previous per-candidate path vs batch path.

The "previous" path reproduces the ``score()`` body at commit 90f6bcd exactly
(validate + two solves per candidate). The "current" path is ``score_many``.

Usage:
    python scripts/benchmark_linucb.py
    python scripts/benchmark_linucb.py --candidates 50 --rounds 20
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.ml.feature_registry import FEATURE_DIMENSION
from app.ml.linucb import SharedLinUCB


def previous_scores(model: SharedLinUCB, vectors: list[np.ndarray]) -> list[float]:
    """The pre-optimisation loop: full validation and two solves per candidate."""
    totals = []
    for x in vectors:
        model._validate()
        theta = np.linalg.solve(model.A, model.b)
        variance = float(x @ np.linalg.solve(model.A, x))
        totals.append(float(theta @ x) + float(model.alpha * np.sqrt(variance)))
    return totals


def current_scores(model: SharedLinUCB, vectors: list[np.ndarray]) -> list[float]:
    return [score.total for score in model.score_many(vectors)]


def timer(fn, model, vectors, rounds: int) -> list[float]:
    samples = []
    for _ in range(rounds):
        start = time.perf_counter()
        fn(model, vectors)
        samples.append((time.perf_counter() - start) * 1000)
    return samples


def build_model(observations: int, seed: int) -> SharedLinUCB:
    model = SharedLinUCB(FEATURE_DIMENSION, ridge=1.0, alpha=0.5)
    rng = np.random.default_rng(seed)
    for _ in range(observations):
        model.observe(rng.normal(size=FEATURE_DIMENSION), float(rng.uniform(0, 0.15)))
    return model


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=int, default=50)
    parser.add_argument("--rounds", type=int, default=20)
    parser.add_argument("--observations", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    model = build_model(args.observations, args.seed)
    rng = np.random.default_rng(args.seed + 1)
    vectors = [rng.normal(size=FEATURE_DIMENSION) for _ in range(args.candidates)]

    before = previous_scores(model, vectors)
    after = current_scores(model, vectors)
    max_abs = max(abs(a - b) for a, b in zip(before, after))

    # Warm both paths once so neither pays first-call overhead.
    previous_scores(model, vectors)
    current_scores(model, vectors)

    previous_ms = timer(previous_scores, model, vectors, args.rounds)
    current_ms = timer(current_scores, model, vectors, args.rounds)

    def block(samples: list[float]) -> dict[str, float]:
        ordered = sorted(samples)
        return {
            "p50": round(statistics.median(ordered), 3),
            "p95": round(float(np.percentile(ordered, 95)), 3),
            "mean": round(statistics.fmean(ordered), 3),
        }

    payload = {
        "feature_dimension": FEATURE_DIMENSION,
        "candidates_per_batch": args.candidates,
        "rounds": args.rounds,
        "observations": args.observations,
        "previous_ms": block(previous_ms),
        "current_ms": block(current_ms),
        "speedup_p50": round(statistics.median(previous_ms) / statistics.median(current_ms), 2),
        "max_abs_score_difference": max_abs,
    }
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
