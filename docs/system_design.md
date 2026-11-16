# System Design

End-to-end behavior of Alfa-Kurs: from an entrepreneur's onboarding form to an
updated recommendation policy.

---

## 1. Actors

| Actor | Goal |
|---|---|
| Entrepreneur | Find the right course with minimal search |
| Alfa-Kurs business | Raise conversion from free content to paid courses |
| Algorithm | Learn which course fits which user, and improve with feedback |
| Judge | Verify the system is real, explainable and evaluated fairly |

## 2. End-to-end flow

```
┌──────────────┐
│  Onboarding  │  industry, stage, experience, interests, budget, goals
└──────┬───────┘
       │ POST /api/users/profile
       ▼
┌──────────────┐
│   Profile    │  stored in PostgreSQL (users)
└──────┬───────┘
       │ GET /api/recommendations/{user_id}
       ▼
┌──────────────────────────────────────────────┐
│ 1. Build user block u                         │
│ 2. Retrieve top-50 courses by content match   │
│ 3. For each candidate: x = [u, c, u∘c]        │
│ 4. LinUCB: score = θᵀx + α√(xᵀA⁻¹x)           │
│ 5. Rank, take top-N                           │
│ 6. Write one slate of recommendation_impressions│
└──────┬───────────────────────────────────────┘
       │
       ▼
┌──────────────┐   click / inspect / purchase   ┌───────────────┐
│ Personalized │ ─────────────────────────────► │ Interaction   │
│    feed      │   (references impression_id)   │  event log    │
└──────────────┘                                └───────┬───────┘
                                                        │ reward
                                                        ▼
                                                ┌───────────────┐
                                                │ LinUCB update │
                                                │ A, b, θ       │
                                                └───────┬───────┘
                                                        │ persisted
                                                        ▼
                                                ┌───────────────┐
                                                │ BanditState   │
                                                └───────────────┘
```

## 3. Why retrieval and ranking are separate

- **Retrieval** is cheap, deterministic and content-based. It removes most of the
  catalogue that has nothing to do with the user.
- **Ranking** is expensive to learn and depends on behavior. It orders the small
  candidate set.

If retrieval returned everything, LinUCB would waste exploration on irrelevant
courses and learn noise. If ranking were skipped, the feed would be "most similar",
which ignores what actually converts.

## 4. Feature vector design

For a (user, course) pair, `x` is a fixed-length numeric vector:

```
x = [ user_block | course_block | interaction_block ]
```

| Block | Dims | Example features | Notes |
|---|---|---|---|
| User | `2K + 5` | interests per category, industry prior, experience, stage one-hot, budget sensitivity | normalized to [0,1] |
| Course | `K + 5` | category one-hot, difficulty, duration, price, has_free, skills count | numeric normalized |
| Interaction | `K + 5` | interest×category, interest match, experience–difficulty fit, goal–skill overlap, free×budget, price×budget | the personalization core |

`K` = number of categories (6 in the sample catalogue), so `d = 4K + 15 = 39`.

There is **no hour, device or session-depth block**. Those features had no concrete
data source and no measured benefit; they were removed from the MVP.

Design rules:

- Same length and order for every candidate (the bandit needs a stable layout).
- All values finite and in `[0,1]`, `float32`, so no single feature dominates.
- The interaction block is what lets a **shared** model personalize: the same weights
  behave differently per user because `interest × category` differs.

Full formulas, encoding maps and normalization rules:
[`feature_engineering.md`](feature_engineering.md). That file is the contract; the
code must match it.

## 5. Recommendation output and the impression record

Each displayed course produces **one** `recommendation_impressions` row containing:

```
user_id, course_id, slate_id, position,
retrieval_score, bandit_score, algorithm, model_version, shown_at
```

There is no separate impressions table. The slate is written in the same transaction
as the ranking result, so the denominator for CTR and conversion always exists.

Each recommendation includes a human-usable **reason**, e.g.:

- "Matches your interest in marketing and sales."
- "Free material available — try before buying."
- "Fits your experience level."

The reason is derived from the dominant matching signal (the interaction features),
not invented by a model.

## 6. Event model

| Event | When | Reward | Stored |
|---|---|---|---|
| impression | course shown | 0 | `recommendation_impressions` row |
| click | course opened | +1 | interaction row |
| inspect | free material examined | +1 | interaction row |
| purchase | paid course bought | +10 | interaction row |
| no_interaction | shown, ignored | 0 | nothing — absence of rows |

Each event is one row and references `impression_id`. A purchase never emits a click
row. Rewards come from `reward_engine.py`; weights are configurable.

A purchase **supplements** earlier engagement but is capped per impression by a unique
`(impression_id, event_type)` constraint, so one impression contributes at most
`1 + 1 + 10 = 12`. See [`reward_design.md`](reward_design.md).

## 7. Consistency guarantees

- The whole slate (`recommendation_impressions`) is written in one transaction.
- An interaction requires an existing impression for that `(user, course)` pair.
- Bandit update happens after the interaction row is committed, so a crash cannot
  apply a reward twice.
- Delayed purchases are attributed via `impression_id` within
  `PURCHASE_ATTRIBUTION_DAYS` (default 7).
- Model version is stored on every impression and every bandit state row.

## 8. Failure behavior

| Failure | Response |
|---|---|
| Retriever returns nothing | fall back to popular courses (past window) |
| LinUCB artifact missing / feature version mismatch | cold start: fresh `A`, explore |
| Non-finite score | log, exclude candidate, continue |
| Impression older than attribution window | `409`, no bandit update |
| DB down | `503`, no partial writes |

## 9. Extension points (documented, not built)

- Natural-language profile extraction (optional LLM service) that fills the same
  `users` fields — the rest of the system would not change.
- Per-segment bandits once traffic justifies them.
- ANN retrieval (FAISS) if the catalogue grows past tens of thousands.
- Online A/B testing framework.

Explicitly out of scope for this project: LLM in the loop, RAG, multi-agent systems,
Telegram bot, FAISS, deep RL, microservices, Kafka, Kubernetes.
