# ML Architecture

The machine-learning half of the system: course features, retrieval, LinUCB,
rewards, evaluation. Everything here is implemented in `backend/app/ml/` and reused
by `experiments/`.

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

## 2. Course feature pipeline

1. **Validate** required fields: id, title, description, category, difficulty,
   duration, price, has_free_material.
2. **Clean** text: lowercase, strip HTML, collapse whitespace.
3. **Normalize** numerics: price and duration to [0,1]; difficulty to an ordinal
   `{beginner:0, intermediate:0.5, advanced:1}`.
4. **Encode** category as one-hot.
5. **Build text** for retrieval: `title + description + skills + objectives`.

## 3. Retrieval — two interchangeable implementations

Both expose `fit(courses)` and `query(user_profile, k=50) -> list[course_id]`.

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
- Stored as a second retriever so the two can be compared empirically.

**Why not FAISS:** the catalogue is small (hundreds of courses). Exact cosine is
`O(n·d)` and trivially fast. ANN adds complexity for no benefit here.

## 4. LinUCB — the ranking policy

Full derivation in [`linucb_explained.md`](linucb_explained.md). Summary:

```
A ← I_d                     (d×d identity + small ridge)
b ← 0_d
θ = A⁻¹ b
score(x) = θᵀx + α √(xᵀ A⁻¹ x)
update:  A ← A + x xᵀ ;  b ← b + r x
```

- `θᵀx` — expected reward from what the model has learned (exploitation).
- `α √(xᵀA⁻¹x)` — uncertainty bonus; large for under-explored directions.
- `A` accumulates information; `A⁻¹` shrinks uncertainty as data arrives.

One shared model across users initially (documented trade-off: fewer parameters
given limited data). Context `x` already includes user features, so one model can
still personalize.

## 5. Reward engine

| Event | Reward | Rationale |
|---|---|---|
| click | +1 | interest signal |
| inspect | +1 | deeper interest (free material) |
| purchase | +10 | strongest signal, rare |
| no_interaction | 0 | explicit absence of signal |

Weights live in settings, not in code. Reward computation is isolated so the bandit
never guesses semantics. See [`reward_design.md`](reward_design.md).

## 6. Synthetic user simulator

Purpose: test the policy without real traffic, reproducibly.

Each simulated user has:

- a hidden preference vector over categories,
- an industry and business stage,
- stochastic behavior:

```
P(click)      = clip(w_click  * match + noise)
P(inspect)    = clip(w_insp   * match + noise)  | click
P(purchase)   = clip(w_buy    * match + noise)  | inspect
P(no action)  = remainder
```

`match = cosine(hidden_preferences, course_category_profile)`.

The algorithm receives only observable features; the simulator alone knows the
hidden vector. Seeds make runs reproducible.

## 7. Evaluation

| Metric | Meaning |
|---|---|
| Cumulative reward | total signal collected |
| Cumulative regret | gap to an oracle that knows preferences |
| CTR | clicks / impressions |
| Conversion | purchases / impressions |
| Precision@K / Recall@K | relevance of top-K |
| NDCG@K | ranking quality with position discount |
| Exploration share | fraction of non-greedy picks |

Compare **Random**, **Top Popular** (past-window only), **LinUCB**, same candidates,
same users, multiple seeds, report mean and confidence interval.

## 8. Boundaries

- `ml/` never imports FastAPI, never opens a DB session.
- `services/` owns transactions and combines modules.
- Retrieval and ranking stay separate.
- No LLM in the loop.

## 9. What to learn

1. TF-IDF and cosine similarity.
2. Why bandits exist vs supervised learning.
3. Ridge regression (LinUCB is ridge regression + uncertainty).
4. Numerical stability when inverting matrices.
5. Evaluation with baselines and confidence intervals.
