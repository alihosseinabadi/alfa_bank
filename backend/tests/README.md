# backend/tests/

Unit and integration tests. Fast, isolated, and focused on the parts that break
silently.

## Files

| File | Covers |
|---|---|
| `test_data_validation.py` | catalogue schema, `source`, bad-row rejection |
| `test_features.py` | `d = 4K + 15`, range `[0,1]`, finiteness, observable-only inputs |
| `test_linucb.py` | score/update correctness, stability, persistence, version mismatch |
| `test_retrieval.py` | top-k shape, ordering, relevance sanity, interface parity |
| `test_rewards.py` | reward values, configurable weights, no double counting |
| `test_attribution.py` | impression linkage, 7-day window, duplicate purchase |
| `test_evaluation.py` | identical users/candidates, same reward engine, CI helper |
| `test_leakage.py` | popularity past-window only, hidden prefs unreachable, import graph |
| `test_api.py` | endpoint contracts, status codes, impression logging |
| `conftest.py` (planned) | fixtures: test DB, client, seeded catalogue |

## What each must assert

**test_features.py**
- `len(x) == d` for every (profile, course) pair.
- All values finite and in `[0,1]`.
- Feature order matches `FEATURE_LAYOUT`.
- The builder cannot receive hidden preferences (signature assertion).

**test_linucb.py**
- `A` remains symmetric positive definite after many updates.
- Scores finite for extreme feature values.
- Save -> load -> identical decisions.
- Wrong `d` or `feature_version` is rejected.
- Repeated (context, reward) converges theta.

**test_retrieval.py**
- Returns at most `k`, sorted by descending score.
- A marketing-interest query surfaces marketing courses.
- Both retrievers satisfy the same interface.

**test_rewards.py**
- click = 1, inspect = 1, purchase = 10, unknown type raises.
- Weights read from settings, not hardcoded.
- A purchase flow adds exactly one purchase row, not click + inspect + purchase.
- Total reward per impression cannot exceed 12.

**test_attribution.py**
- Purchase without impression -> 409.
- Purchase older than `PURCHASE_ATTRIBUTION_DAYS` -> 409.
- Valid purchase updates the bandit with that impression's context.
- Second purchase of the same course by the same user -> 409.

**test_evaluation.py**
- Same user population across policies for a seed.
- Same candidate list per round across policies.
- Same reward engine instance for all policies.
- 10 seeds produce 10 independent records.
- Mean/CI helper brackets the mean.

**test_leakage.py**
- Popularity never reads events at or after `window_start`.
- `ml/` does not import `experiments/`.
- Oracle is unreachable from policy constructors.

**test_api.py**
- Each route returns the documented status code.
- Recommendations write one row per item in `recommendation_impressions`.
- Duplicate events return 409.
- No 200 responses carrying error bodies.

## Run

```bash
pytest backend/tests -q
pytest backend/tests/test_linucb.py -q -k stability
```

## Philosophy

Tests protect the three things that are easy to get wrong and expensive to debug:
the ML math, the event accounting, and the fairness of the evaluation. UI tests are
out of scope.

## What to learn

Fixtures, parameterization, testing numeric code with tolerances
(`np.allclose`), and testing invariants (uniqueness, window boundaries) instead of
implementation details.
