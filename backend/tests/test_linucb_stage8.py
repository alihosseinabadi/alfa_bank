import numpy as np
import pytest
from app.ml.linucb import SharedLinUCB

def test_score_and_reward_revision():
    m = SharedLinUCB(2, ridge=2, alpha=0.5)
    s = m.score([1, 0])
    assert s.exploit == 0 and s.explore == pytest.approx(0.5 / np.sqrt(2))
    m.observe([1, 0], 0)
    A = m.A.copy()
    m.revise([1, 0], 0, 0.5)
    np.testing.assert_array_equal(m.A, A)
    assert m.b[0] == .5
    assert m.score([1, 0]).exploit == pytest.approx(1 / 6)

def test_invalid_inputs_are_rejected_without_mutation():
    m = SharedLinUCB(2)
    for x, reward in [([float('nan'), 0], 1), ([1], 0), ([1, 0], 2)]:
        with pytest.raises(ValueError): m.observe(x, reward)
    np.testing.assert_array_equal(m.A, np.eye(2))
    with pytest.raises(ValueError): SharedLinUCB(2, A=[[1, 1], [0, 1]])
    with pytest.raises(ValueError): SharedLinUCB(2, A=[[1, 0], [0, -1]])

def test_mutation_invalidates_model_provenance():
    m = SharedLinUCB(2)
    m.state_id = 'old'
    m.observe([1,0], .5)
    assert m.state_id is None
    m.state_id = 'new'
    m.revise([1,0], .5, 1)
    assert m.state_id is None
