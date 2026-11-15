# LinUCB batch scoring — Phase 5.1

Date: 2026-11-15. Branch `ml-boost`.

## Problem

`SharedLinUCB.score()` validated the whole model state on **every** call:

```python
def score(self, x):
    self._validate()                      # shape, finiteness, symmetry, Cholesky, np.linalg.cond
    theta = np.linalg.solve(self.A, self.b)
    variance = float(x @ np.linalg.solve(self.A, x))
```

`_validate()` runs `np.linalg.cholesky` **and** `np.linalg.cond`, and `cond` is a
singular-value computation. With a 45-dimensional feature vector and 50 candidates
per slate, that is 50 Cholesky factorisations and 50 condition-number estimates for
one ranking call — all of them on the same matrix.

## Change

`backend/app/ml/linucb.py`:

* `_ensure_cached()` computes the inverse and `theta = A⁻¹b` **once per state**, guarded
  by `state_digest()`. If `A` or `b` changes by any route — `observe`, `revise`, or a
  direct attribute mutation — the digest no longer matches and the state is
  re-validated and re-inverted before use.
* `score_many(features)` validates once, then scores the batch with cached
  `A⁻¹`: `exploit = theta·x`, `variance = xᵀA⁻¹x`.
* `score(x)` keeps its exact signature and semantics; it now uses the cache.
* An empty batch returns `[]` **without** touching the state, so an invalid model with
  no candidates still produces the old "no scores needed" behaviour instead of raising.

Safety checks were moved, not removed: shape, finiteness, symmetry, positive
definiteness and the condition-number ceiling all still run, once per state change
rather than once per candidate. Provenance is untouched — `state_digest()` is
byte-identical to before, so `matrix_digest` comparisons in `ucb_ranking.py` and
`learning_checkpoint.py` behave exactly as they did.

`backend/app/ml/ucb_ranking.py` now builds the vector list and calls `score_many`
once. Ranking order, scores and the `shared-linucb-ranking-v1` version string are
unchanged.

## Equivalence evidence

`backend/tests/test_linucb_batch.py` (7 tests) re-implements the pre-change `score()`
body verbatim as `legacy_score` and asserts:

| test | asserts |
|---|---|
| `test_batch_scores_match_the_previous_implementation` | 50 candidates after 10 `observe` + 1 `revise`: exploit, explore and total match to `rel=1e-9` |
| `test_single_score_still_matches_the_previous_implementation` | per-call `score()` also matches |
| `test_state_change_invalidates_the_cached_inverse` | `observe` changes the result, and it matches the legacy computation |
| `test_safety_checks_survive_a_direct_mutation` | asymmetric `A` written directly still raises `ValueError` |
| `test_corrupted_state_is_rejected_before_any_scoring` | `NaN` in `b` still raises |
| `test_empty_batch_does_not_touch_the_state` | corrupted state + empty batch does not raise |
| `test_provenance_digest_is_unchanged_by_scoring` | scoring never changes `state_digest()` |

Measured maximum absolute score difference on 50 random candidates:
**1.11e-16** (float64 round-off from using `A⁻¹` instead of re-solving).

## Latency, before and after

```powershell
$env:PYTHONUTF8=1; python scripts/benchmark_linucb.py --json data/synthetic/linucb_benchmark_v1.json
```

Environment: Windows 11, Python 3.12.10, numpy 2.5.3, CPU only. 45 features,
50 candidates per batch, model fitted with 200 observations, 20 timed rounds after a
warm-up pass.

| path | p50 ms | p95 ms | mean ms |
|---|---|---|---|
| previous (validate + 2 solves per candidate) | **30.50** | 35.05 | 31.36 |
| current (one validation + cached inverse) | **1.10** | 1.63 | 1.19 |
| **speedup** | **27.8×** | 21.5× | 26.4× |

The acceptance target was ≥ 5× with numerically matching scores. Measured: 27.8× at
p50, max score difference 1.11e-16.

## What this does not prove

* The absolute numbers are for a 45-dimensional model with 50 candidates; a wider
  feature space shifts both columns, and the ratio should grow (the per-candidate
  validation cost is `O(d³)`, the cached per-candidate cost is `O(d²)`).
* This is scoring latency only. `rank_ucb` still calls `validate_features` per
  candidate; that is a Pydantic-level check and was not part of this task.
* The end-to-end request path is not measured here — there is no running service in
  this environment (no Postgres, no API server).
* Cache correctness relies on `state_digest()` covering `A` and `b`. It does: the
  digest hashes `A.tobytes()` and `b.tobytes()` plus the hyperparameters. Any future
  mutable field added to the model must be added to that digest, or the cache will go
  stale.
