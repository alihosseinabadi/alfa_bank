# backend/app/ml/

Pure machine-learning modules. No FastAPI, no SQLAlchemy, no I/O side effects beyond
explicit artifact save/load. Reused by the API and by `experiments/`.

## Files

| File | Responsibility | Depends on |
|---|---|---|
| `feature_engineering.py` | clean courses, build user/course/context vectors `x` | Pandas, NumPy |
| `tfidf_retriever.py` | TF-IDF fit + cosine top-k | scikit-learn |
| `embedding_retriever.py` | sentence-transformer fit + cosine top-k | sentence-transformers |
| `linucb.py` | LinUCB score/select/update, persistence hooks | NumPy |
| `reward_engine.py` | event type -> reward | `core/config` |
| `model_persistence.py` | save/load `A`, `b`, version | joblib/NumPy |

## Shared retriever interface

```python
class Retriever(Protocol):
    def fit(self, courses: list[CourseRecord]) -> None: ...
    def query(self, profile: dict, k: int = 50) -> list[str]: ...
```

Both retrievers must be interchangeable so experiments can compare them without
touching callers.

## Feature vector contract

- Fixed length `d` for every candidate.
- Layout documented in one constant; asserted in tests.
- All values finite and roughly `[0, 1]`.

## LinUCB contract

```python
score(context: np.ndarray) -> float
select(candidates: list[np.ndarray]) -> int
update(context: np.ndarray, reward: float) -> None
save(path) / load(path)
```

## Rules

- Deterministic given a seed.
- No global mutable state; a model instance is passed in.
- Numerical safety is enforced here (ridge, `solve`, finiteness checks).
- Never import from `api/`, `services/`, or `models/`.

## Tests

```bash
pytest backend/tests/test_linucb.py backend/tests/test_retrieval.py backend/tests/test_rewards.py -q
```

## What to learn

TF-IDF, cosine similarity, ridge regression, the LinUCB optimism bonus, and how to
keep an algorithm library framework-free so it is easy to test.
