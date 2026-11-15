"""Batch scoring must return exactly what per-candidate scoring returned.

The speedup in ``SharedLinUCB`` moved validation and matrix inversion out of
``score()`` and into a digest-guarded cache. This module pins the two things that
could silently break:

1. the numbers are the same (including after ``observe`` and ``revise``);
2. the safety checks still fire on a corrupted state, even when the corruption is
   a direct attribute mutation that bypasses the mutation methods.
"""
import numpy as np
import pytest

from app.ml.linucb import SharedLinUCB


def legacy_score(model, x):
    """The exact ``score()`` body before the batch optimisation (commit 90f6bcd)."""
    model._validate()
    x = np.asarray(x, dtype=np.float64)
    theta = np.linalg.solve(model.A, model.b)
    variance = float(x @ np.linalg.solve(model.A, x))
    if not np.isfinite(variance) or variance < 0:
        raise ValueError("invalid uncertainty")
    exploit = float(theta @ x)
    explore = float(model.alpha * np.sqrt(variance))
    return exploit, explore, exploit + explore


def _batch(dimension, count, seed):
    rng = np.random.default_rng(seed)
    return rng.normal(size=(count, dimension))


def test_batch_scores_match_the_previous_implementation():
    model = SharedLinUCB(8, ridge=1.0, alpha=0.5)
    vectors = _batch(8, 50, seed=11)
    for index, vector in enumerate(vectors[:10]):
        model.observe(vector, (index % 3) / 2)
    model.revise(vectors[0], 0.0, 0.5)

    expected = [legacy_score(model, vector) for vector in vectors]
    actual = model.score_many(vectors)
    assert len(actual) == 50
    for (exploit, explore, total), score in zip(expected, actual):
        assert score.exploit == pytest.approx(exploit, rel=1e-9, abs=1e-12)
        assert score.explore == pytest.approx(explore, rel=1e-9, abs=1e-12)
        assert score.total == pytest.approx(total, rel=1e-9, abs=1e-12)


def test_single_score_still_matches_the_previous_implementation():
    model = SharedLinUCB(4, ridge=2.0, alpha=0.3)
    model.observe([1.0, 0.0, 0.5, -0.5], 1.0)
    for vector in _batch(4, 20, seed=5):
        exploit, explore, total = legacy_score(model, vector)
        score = model.score(vector)
        assert score.exploit == pytest.approx(exploit, rel=1e-9, abs=1e-12)
        assert score.total == pytest.approx(total, rel=1e-9, abs=1e-12)


def test_state_change_invalidates_the_cached_inverse():
    model = SharedLinUCB(3, ridge=1.0, alpha=1.0)
    before = model.score([1.0, 1.0, 0.0])
    model.observe([1.0, 1.0, 0.0], 1.0)
    after = model.score([1.0, 1.0, 0.0])
    assert after.total != before.total
    assert after.total == pytest.approx(legacy_score(model, [1.0, 1.0, 0.0])[2], rel=1e-9)


def test_safety_checks_survive_a_direct_mutation():
    model = SharedLinUCB(2, ridge=1.0)
    model.score([1.0, 0.0])  # warm the cache
    model.A[0, 1] = 10.0     # asymmetric, bypassing observe/revise
    with pytest.raises(ValueError):
        model.score_many([[1.0, 0.0]])


def test_corrupted_state_is_rejected_before_any_scoring():
    model = SharedLinUCB(2, ridge=1.0)
    model.score([1.0, 0.0])
    model.b[0] = float("nan")
    with pytest.raises(ValueError):
        model.score_many([[1.0, 0.0]])


def test_empty_batch_does_not_touch_the_state():
    model = SharedLinUCB(2)
    model.A[0, 1] = 10.0  # corrupt, but an empty batch must not raise
    assert model.score_many([]) == []


def test_provenance_digest_is_unchanged_by_scoring():
    model = SharedLinUCB(3, ridge=1.0, alpha=0.5)
    model.observe([1.0, 0.0, 0.0], 0.5)
    model.matrix_digest = model.state_digest()
    model.score_many(_batch(3, 10, seed=2))
    assert model.state_digest() == model.matrix_digest
