# ML Architecture

The machine-learning half of the system: features, retrieval, LinUCB, rewards,
evaluation. Implemented in `backend/app/ml/` and reused by `experiments/`.

---

## 1. Pipeline

```
course text ──► TF-IDF / embeddings ──► candidate set (top 50)
                                              │
user profile ──► feature builder ─────────────┤
                                              ▼
                                   context vectors x
                                              │
                                    LinUCB scoring
                                              │
                                     ranked list (top N)
                                              │
                                        user feedback
                                              │
                                     reward engine
                                              │
                                       LinUCB update
```

## 2. Course data pipeline

1. **Validate** required fields: id, title, description, category, difficulty,
   duration, price, has_free_material, **source**.
2. **Clean** text: lowercase, strip HTML, collapse whitespace.
3. **Normalize** numerics: price and duration to [0,1]; difficulty to an ordinal.
4. **Encode** category as one-hot in a fixed category order.
5. **Build text** for retrieval: `title + description + skills + objectives`.

Validation and normalization rules live in
[`feature_engineering.md`](feature_engineering.md); the loader is
`ml/feature_engineering.py`.

## 3. Retrieval — two interchangeable implementations

Both expose `fit(courses)` and `query(profile, k=50) -> list[course_id]`.

### 3.1 TF-IDF

```
tf-idf(t, d) = tf(t, d) * idf(t)
idf(t) = log((1 + n) / (1 + df(t))) + 1
similarity = (u · d) / (||u|| ||d||)
```

- Deterministic, fast, no downloads.
- Weak on synonyms ("advertising" vs "marketing").
- Primary retriever for the hackathon.

### 3.2 Sentence embeddings

- Encode each course text once at startup; encode the user's interest text per query.
- Cosine similarity in the same space.
- Stronger semantic matching; heavier dependency.
- Kept as a second retriever so the two can be compared empirically.

**Why not FAISS:** the catalogue is small (hundreds of courses). Exact cosine is
`O(n·d)` and trivially fast. ANN adds complexity for no benefit here.

## 4. Context vector

```
x = [ user_block | course_block | interaction_block ]      d = 4K + 15
```

The **interaction block** is what personalizes a shared model:

| Feature | Formula |
|---|---|
| `interest_x_category[k]` | `interest[k] * course_onehot[k]` |
| `interest_match` | `cosine(interests, course_category_profile)` |
| `exp_diff_fit` | `1 - abs(exp_ordinal - diff_ordinal)` |
| `goal_skill_overlap` | `len(goals ∩ skills) / max(len(goals),1)` |
| `free_pref_x_free` | `budget_sensitivity * has_free` |
| `price_x_budget` | `price_norm * (1 - budget_sensitivity)` |

No device, hour or session-depth features. Only observable inputs; hidden simulator
preferences never enter `x`. Full spec:
[`feature_engineering.md`](feature_engineering.md).

## 5. LinUCB — the ranking policy

Full derivation in [`linucb_explained.md`](linucb_explained.md). Summary:

```
A ← λI_d
b ← 0_d
θ = A⁻¹ b
score(x) = θᵀx + α √(xᵀ A⁻¹ x)
update:  A ← A + x xᵀ ;  b ← b + r x
```

- `θᵀx` — expected reward from what the model has learned (exploitation).
- `α √(xᵀA⁻¹x)` — uncertainty bonus; large for under-explored directions.
- `A` accumulates information; `A⁻¹` shrinks uncertainty as data arrives.

One shared model across users. Personalization comes from the interaction block, not
from per-user parameters. Per-segment models are future work.

## 6. Reward engine

| Event | Reward | Rationale |
|---|---|---|
| impression, no engagement | 0 | denominator only, no reward row |
| click | +1 | interest signal |
| inspect | +1 | deeper interest (free material) |
| purchase | +10 | strongest signal, rare |

Weights live in settings, not in code. Reward computation is isolated so the bandit
never guesses semantics. A purchase **supplements** earlier events but is capped per
impression (`1 + 1 + 10 = 12` max) and never expanded into click rewards. Delayed
purchases are attributed through `impression_id` within a 7-day window. See
[`reward_design.md`](reward_design.md).

## 7. Synthetic user simulator

Purpose: test the policy without real traffic, reproducibly.

Each simulated user has:

- a hidden preference vector over categories,
- an industry, stage, experience, budget sensitivity,
- stochastic behavior:

```
P(click)    = clip(w_click   * match + noise)
P(inspect)  = clip(w_inspect * match + noise)  | click
P(purchase) = clip(w_buy     * match + noise)  | inspect
P(no action)= remainder
```

`match = cosine(hidden_preferences, course_category_profile)`.

The policy receives only observable features. Only the simulator and the oracle see
the hidden vector. Seeds make runs reproducible.

## 8. Evaluation

| Metric | Meaning |
|---|---|
| Cumulative reward | total signal collected |
| Cumulative regret | gap to an oracle that knows hidden preferences (simulator only) |
| CTR | clicks / impressions |
| Free-material inspection rate | inspects / impressions |
| Purchase conversion | purchases / impressions |
| Precision@K / Recall@K | relevance of top-K |
| NDCG@K | ranking quality with position discount |
| Exploration share | fraction of non-greedy picks |

Compare **Random**, **Top Popular** (past window only), **LinUCB** with identical
users and candidate sets, over **≥10 seeds**, reporting mean and 95% confidence
intervals. Fairness and leakage are enforced by tests, not prose:
`tests/test_evaluation.py`, `tests/test_leakage.py`.

## 9. Boundaries

- `ml/` never imports FastAPI, never opens a DB session, never imports `experiments/`.
- `services/` owns transactions and combines modules.
- Retrieval and ranking stay separate.
- No LLM, no RAG, no deep RL.

## 10. What to learn

1. TF-IDF and cosine similarity.
2. Why bandits exist vs supervised learning.
3. Ridge regression (LinUCB is ridge regression + uncertainty).
4. Numerical stability when inverting matrices.
5. Evaluation with baselines, multiple seeds and confidence intervals.
