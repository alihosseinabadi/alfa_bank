"""The drift monitor must not confuse absent data with zero performance."""
import pytest

from scripts.monitor_drift import interaction_summary, monitor, retrieval_summary


def retrieval(context_id, status, count, algorithm="light_hybrid"):
    return {
        "context_id": context_id,
        "query": "q",
        "algorithm": algorithm,
        "status": status,
        "candidates": [{"material_key": f"m{i}", "rank": i + 1, "score": 0.5} for i in range(count)],
    }


def event(context_id, material_key, kind, rank=None, channel="light_hybrid"):
    return {
        "context_id": context_id,
        "material_key": material_key,
        "kind": kind,
        "rank": rank,
        "channel": channel,
    }


def test_no_match_rate_and_coverage_are_complementary():
    rows = [
        retrieval("c1", "matched", 5),
        retrieval("c2", "no_eligible", 0),
        retrieval("c3", "needs_clarification", 0),
        retrieval("c4", "matched", 2),
    ]
    summary = retrieval_summary(rows)
    assert summary["calls"] == 4
    assert summary["empty_calls"] == 2
    assert summary["no_match_rate"] == 0.5
    assert summary["coverage"] == pytest.approx(1 - summary["no_match_rate"])
    assert summary["mean_candidates"] == 1.75
    assert summary["by_status"] == {
        "matched": 2, "needs_clarification": 1, "no_eligible": 1,
    }


def test_ctr_is_split_by_position_and_channel():
    events = [
        event("c1", "m1", "impression", rank=1),
        event("c1", "m1", "click", rank=1),
        event("c1", "m2", "impression", rank=2),
        event("c1", "m3", "impression", rank=7),
        event("c2", "m4", "impression", rank=1, channel="tfidf"),
        event("c2", "m4", "open", rank=1, channel="tfidf"),
    ]
    summary = interaction_summary(events)
    assert summary["impressions"] == 4
    assert summary["positives"] == 2
    assert summary["ctr_by_position"]["1-3"] == {"impressions": 3, "positives": 2, "ctr": pytest.approx(0.6667)}
    assert summary["ctr_by_position"]["4-10"]["ctr"] == 0.0
    assert summary["ctr_by_channel"]["tfidf"]["ctr"] == 1.0
    assert summary["ctr_by_channel"]["light_hybrid"]["ctr"] == pytest.approx(0.3333)


def test_unknown_and_malformed_records_do_not_move_the_denominator():
    events = [
        event("c1", "m1", "impression", rank=1),
        event("c1", "m1", "dwell", rank=1),
        {"kind": "click"},
    ]
    summary = interaction_summary(events)
    assert summary["impressions"] == 1
    assert summary["positives"] == 0
    assert summary["ignored_kinds"] == {"dwell": 1, "malformed": 1}


def test_empty_inputs_report_zero_calls_instead_of_dividing_by_zero():
    report = monitor([], [])
    assert report["retrieval"]["calls"] == 0
    assert report["interactions"]["ctr"] is None
    assert report["interactions"]["ctr_by_position"] == {}
