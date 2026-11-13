# backend/app/ml/

Pure machine-learning modules. No FastAPI, no SQLAlchemy, no DB session, and no
import of `experiments/`. Reused by the API and by the offline experiment runner.

## Files

| File | Responsibility | Depends on |
|---|---|---|
| `feature_engineering.py` | validate courses; build `x = [user \| course \| interaction]` | Pandas, NumPy |
| `tfidf_retriever.py` | TF-IDF fit + cosine top-k | scikit-learn |
| `embedding_retriever.py` | sentence-transformer fit + cosine top-k | sentence-transformers |
| `linucb.py` | LinUCB score/select/update, persistence | NumPy |
| `reward_engine.py` | event type -> reward | `core/config` |
| `model_persistence.py` | save/load `A`, `b`, `feature_version` | joblib/NumPy |

## Feature contract

`docs/feature_engineering.md` is authoritative. Key points:

- `x = [user_block | course_block | interaction_block]`
- `d = 4K + 15` (`39` with `K = 6`)
- `float32`, all elements clipped to `[0,1]`
- `FEATURE_LAYOUT` defines order; `FEATURE_VERSION` guards artifacts
- **No** device, hour or session-depth features
- **Never** accepts hidden simulator preferences

The interaction block is what personalizes the shared model:
`interest × category`, `interest_match`, `exp_diff_fit`, `goal_skill_overlap`,
`free_pref × free`, `price × budget`.

## Shared retriever interface

```python
class Retriever(Protocol):
    def fit(self, courses: list[CourseRecord]) -> None: ...
    def query(self, profile: dict, k: int = 50) -> list[str]: ...
```

Both retrievers must be interchangeable so experiments can compare them without
touching callers.

## LinUCB contract

```python
score(context: np.ndarray) -> float
select(candidates: list[np.ndarray]) -> int
update(context: np.ndarray, reward: float) -> None
save(path) / load(path)          # rejects mismatched d or feature_version
```

## Reward contract

| Event | Reward |
|---|---|
| click | +1 |
| inspect | +1 |
| purchase | +10 |
| impression without engagement | 0 (no row) |

Weights come from `core/config.py`. A purchase does not expand into click rewards;
the database caps one event per type per impression.

## Rules

- Deterministic given a seed.
- No global mutable state; a model instance is passed in.
- Numerical safety enforced here: ridge term, `solve`, symmetrize, finiteness checks.
- Never import from `api/`, `services/`, `models/`, or `experiments/`.

## Tests

```bash
pytest backend/tests/test_features.py backend/tests/test_linucb.py \
       backend/tests/test_retrieval.py backend/tests/test_rewards.py -q
```

## What to learn

TF-IDF, cosine similarity, ridge regression, the LinUCB optimism bonus, and how to
keep an algorithm library framework-free so it is easy to test.

## Implemented MVP profile component

profile_contracts.py, profile_policy.py, user_profile.py and request_context.py
implement the stage-4 profile and task-first context with capped evidence,
explicit preferences and historical cutoff. They contain no HTTP or database code.
Runbook: [docs/profiles_stage4.md](../../../docs/profiles_stage4.md).
The demonstration feature/reward contracts above describe later planned modules;
they do not override the current catalog/history/profile interfaces.