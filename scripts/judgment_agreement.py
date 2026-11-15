"""Inter-annotator agreement for graded relevance judgments (Cohen's kappa).

The project's judgment record format is fixed by ``scripts/audit_judgments_stage10.py``::

    {"case_id": "dev001", "material_key": "m17", "grade": 2,
     "assessor": "annotator-a", "scope": "public excerpt", "independent": true}

Grades are 0..3. This script compares two independent label files over the
``(case_id, material_key)`` pairs they share and reports:

* nominal Cohen's kappa (chance-corrected agreement over exact grades),
* quadratic-weighted kappa (ordinal; treating grade 2 vs 3 as a small error rather
  than the same error as 0 vs 3),
* raw exact-agreement rate,
* coverage, so a partial second pass cannot masquerade as full agreement.

Kappa is undefined when both annotators use a single identical grade for everything
(chance agreement is 1). In that case the value is reported as ``null`` with a note,
never as 1.0.

Usage:
    python scripts/judgment_agreement.py --a labels_a.json --b labels_b.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

GRADES = (0, 1, 2, 3)


def _index(labels: list[dict[str, Any]], name: str) -> dict[tuple[str, str], int]:
    indexed: dict[tuple[str, str], int] = {}
    for label in labels:
        key = (label["case_id"], label["material_key"])
        if key in indexed:
            raise ValueError(f"duplicate judgment in {name}: {key}")
        grade = label["grade"]
        if type(grade) is not int or grade not in GRADES:
            raise ValueError(f"invalid grade in {name}: {key}")
        if not label.get("assessor"):
            raise ValueError(f"missing assessor in {name}: {key}")
        indexed[key] = grade
    return indexed


def _kappa_matrix(pairs: list[tuple[int, int]]) -> tuple[float | None, float | None, float]:
    """Return (nominal kappa, quadratic-weighted kappa, observed agreement)."""
    total = len(pairs)
    if total == 0:
        raise ValueError("no shared judgments to compare")
    observed = [[0] * len(GRADES) for _ in GRADES]
    for first, second in pairs:
        observed[first][second] += 1
    row_sums = [sum(row) for row in observed]
    column_sums = [sum(observed[i][j] for i in range(len(GRADES))) for j in range(len(GRADES))]
    observed_agreement = sum(observed[i][i] for i in range(len(GRADES))) / total
    expected_agreement = sum(row_sums[i] * column_sums[i] for i in range(len(GRADES))) / (total * total)

    nominal: float | None
    if expected_agreement >= 1.0:
        nominal = None
    else:
        nominal = (observed_agreement - expected_agreement) / (1.0 - expected_agreement)

    weighted: float | None
    if expected_agreement >= 1.0:
        weighted = None
    else:
        span = len(GRADES) - 1
        disagreement_observed = 0.0
        disagreement_expected = 0.0
        for i in range(len(GRADES)):
            for j in range(len(GRADES)):
                weight = ((i - j) ** 2) / (span ** 2)
                disagreement_observed += weight * observed[i][j]
                disagreement_expected += weight * row_sums[i] * column_sums[j] / total
        weighted = 1.0 - disagreement_observed / disagreement_expected if disagreement_expected else None
    return nominal, weighted, observed_agreement


def agreement(labels_a: list[dict[str, Any]], labels_b: list[dict[str, Any]]) -> dict[str, Any]:
    first = _index(labels_a, "first file")
    second = _index(labels_b, "second file")
    shared = sorted(set(first) & set(second))
    only_first = len(set(first) - set(second))
    only_second = len(set(second) - set(first))
    pairs = [(first[key], second[key]) for key in shared]
    nominal, weighted, observed = _kappa_matrix(pairs)

    disagreements = [
        {"case_id": key[0], "material_key": key[1], "a": first[key], "b": second[key]}
        for key in shared
        if first[key] != second[key]
    ]
    label_totals = Counter()
    for pair in pairs:
        label_totals[pair[0]] += 0
    counts_a = Counter(first[key] for key in shared)
    counts_b = Counter(second[key] for key in shared)
    return {
        "shared_pairs": len(shared),
        "only_in_a": only_first,
        "only_in_b": only_second,
        "coverage_of_a": round(len(shared) / len(first), 4) if first else 0.0,
        "coverage_of_b": round(len(shared) / len(second), 4) if second else 0.0,
        "exact_agreement": round(observed, 4),
        "cohen_kappa": round(nominal, 4) if nominal is not None else None,
        "quadratic_weighted_kappa": round(weighted, 4) if weighted is not None else None,
        "grades_a": dict(sorted(counts_a.items())),
        "grades_b": dict(sorted(counts_b.items())),
        "disagreements": len(disagreements),
        "disagreement_examples": disagreements[:10],
        "note": (
            "Kappa is null when chance agreement is 1 (both annotators used one "
            "grade for every shared pair); that is undefined, not perfect agreement."
            if nominal is None else None
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--a", type=Path, required=True)
    parser.add_argument("--b", type=Path, required=True)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    raw_a = args.a.read_bytes()
    raw_b = args.b.read_bytes()
    result = agreement(json.loads(raw_a), json.loads(raw_b))
    result.update(
        a_sha256=hashlib.sha256(raw_a).hexdigest(),
        b_sha256=hashlib.sha256(raw_b).hexdigest(),
    )
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8", newline="\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
