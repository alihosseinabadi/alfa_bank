"""Inter-annotator agreement must be computed honestly, including its edge cases."""
import pytest

from scripts.judgment_agreement import agreement


def label(case_id, material_key, grade, assessor="a"):
    return {
        "case_id": case_id,
        "material_key": material_key,
        "grade": grade,
        "assessor": assessor,
        "scope": "public excerpt",
        "independent": True,
    }


def test_identical_label_files_give_kappa_one():
    rows = [label("q1", "m1", 2), label("q1", "m2", 0), label("q2", "m1", 1), label("q2", "m2", 3)]
    result = agreement(rows, [dict(row, assessor="b") for row in rows])
    assert result["exact_agreement"] == 1.0
    assert result["cohen_kappa"] == 1.0
    assert result["quadratic_weighted_kappa"] == 1.0
    assert result["disagreements"] == 0


def test_near_disagreement_is_penalised_less_by_the_weighted_kappa():
    rows = [label("q1", f"m{i}", grade) for i, grade in enumerate([0, 0, 1, 1, 2, 2, 3, 3])]
    other = [dict(row, assessor="b") for row in rows]
    for row in other[:4]:
        row["grade"] = min(3, row["grade"] + 1)
    result = agreement(rows, other)
    assert result["exact_agreement"] == 0.5
    assert result["quadratic_weighted_kappa"] > result["cohen_kappa"]


def test_partial_second_pass_reports_coverage_not_full_agreement():
    rows = [label("q1", "m1", 2), label("q1", "m2", 0), label("q2", "m1", 1)]
    other = [label("q1", "m1", 2, assessor="b")]
    result = agreement(rows, other)
    assert result["shared_pairs"] == 1
    assert result["coverage_of_b"] == pytest.approx(1.0)
    assert result["coverage_of_a"] == pytest.approx(1 / 3, abs=1e-4)
    assert result["only_in_a"] == 2


def test_constant_labels_report_undefined_kappa_not_one():
    rows = [label("q1", "m1", 2), label("q1", "m2", 2)]
    other = [label("q1", "m1", 2, assessor="b"), label("q1", "m2", 2, assessor="b")]
    result = agreement(rows, other)
    assert result["cohen_kappa"] is None
    assert result["coverage_of_a"] == 1.0
    assert "undefined" in result["note"]


def test_invalid_and_duplicate_labels_are_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        agreement([label("q1", "m1", 2), label("q1", "m1", 1)], [])
    with pytest.raises(ValueError, match="invalid grade"):
        agreement([label("q1", "m1", 4)], [])
    with pytest.raises(ValueError, match="missing assessor"):
        agreement([label("q1", "m1", 2, assessor="")], [])
    with pytest.raises(ValueError, match="no shared"):
        agreement([label("q1", "m1", 2)], [label("q2", "m9", 1, assessor="b")])
