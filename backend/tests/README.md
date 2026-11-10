# backend/tests/

Unit and integration tests. Fast, isolated, and focused on the parts that break
silently.

## Files

| File | Covers |
|---|---|
| `test_linucb.py` | score/update correctness, stability, persistence |
| `test_retrieval.py` | top-k shape, ordering, relevance sanity |
| `test_rewards.py` | reward values, no double counting, unknown events |
| `test_api.py` | endpoint contracts, status codes, impression logging |
| `conftest.py` (planned) | fixtures: test DB, client, seeded catalogue |

## What each must assert

**test_linucb.py**
- `A` remains symmetric positive definite after many updates.
- Scores are finite for extreme feature values.
- Save -> load -> identical decisions.
- A repeated (context, reward) converges theta.

**test_retrieval.py**
- Returns at most `k`, sorted by descending score.
- A marketing-interest query surfaces marketing courses.
- Both retrievers satisfy the same interface.

**test_rewards.py**
- click=1, inspect=1, purchase=10, no_interaction=0.
- Purchase flow adds exactly one reward (no click reward attached).
- Unknown event type raises.

**test_api.py**
- Each route returns the documented status code.
- Recommendations write impressions.
- Purchase without impression returns 404/409 as designed.
- No 200 responses carrying error bodies.

## Run

```bash
pytest backend/tests -q
pytest backend/tests/test_linucb.py -q -k stability
```

## Philosophy

Tests here protect the two things that are easy to get wrong and expensive to debug:
the ML math and the event accounting. UI tests are out of scope.

## What to learn

Fixtures, parameterization, and testing numeric code with tolerances
(`np.allclose`) instead of exact equality.
