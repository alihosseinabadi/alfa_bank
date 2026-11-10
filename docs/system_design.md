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
│  Onboarding  │  industry, stage, experience, interests, goals
└──────┬───────┘
       │ POST /api/users/profile
       ▼
┌──────────────┐
│   Profile    │  stored in PostgreSQL (users)
└──────┬───────┘
       │ GET /api/recommendations/{user_id}
       ▼
┌──────────────────────────────────────────────┐
│ 1. Build user vector u                        │
│ 2. Retrieve top-50 courses by content match   │
│ 3. For each candidate: x = [u, c, ctx]        │
│ 4. LinUCB: score = θᵀx + α√(xᵀA⁻¹x)           │
│ 5. Rank, take top-N                           │
│ 6. Persist Recommendation + Impression rows   │
└──────┬───────────────────────────────────────┘
       │
       ▼
┌──────────────┐   click / inspect / purchase   ┌───────────────┐
│ Personalized │ ─────────────────────────────► │ Interaction   │
│    feed      │                                │  event log    │
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

- **Retrieval** is cheap, deterministic and content-based. It removes 90% of the
  catalogue that has nothing to do with the user.
- **Ranking** is expensive to learn and depends on behavior. It orders the small
  candidate set.

If retrieval returned everything, LinUCB would waste exploration on irrelevant
courses and learn noise. If ranking were skipped, the feed would be "most similar"
which ignores what actually converts.

## 4. Feature vector design

For a (user, course, context) triple, `x` is a fixed-length numeric vector:

| Block | Example features | Notes |
|---|---|---|
| User | interest scores per category, experience (ordinal), stage one-hot | normalized to [0,1] |
| Course | category one-hot, difficulty (ordinal), duration, price, has_free | numeric normalized |
| Context | hour bucket, device, session depth | small, bounded |

Design rules:

- Same length and order for every candidate (the bandit needs a stable layout).
- All values finite and roughly in [0,1] so no single feature dominates.
- Category one-hots let the model learn "marketing lovers click marketing".

Dimension is documented once in `ml/feature_engineering.py` and asserted in tests.

## 5. Recommendation output

Each recommendation includes a human-usable **reason**, e.g.:

- "Matches your interest in marketing and sales."
- "Popular with founders at your stage."
- "Free material available — try before buying."

The reason is derived from the dominant matching signal, not invented by a model.

## 6. Event model

| Event | When | Reward |
|---|---|---|
| impression | course shown | 0 |
| click | course opened | +1 |
| inspect | free material examined | +1 |
| purchase | paid course bought | +10 |
| no_interaction | shown, ignored | 0 |

Each event is one row. A purchase never emits a click row. Summing rewards over
events gives the learning signal. Rewards are computed by `reward_engine.py`.

## 7. Consistency guarantees

- Impression is written in the same transaction as the recommendation.
- Interaction requires an existing impression for that (user, course, recommendation).
- Bandit update happens after the interaction row is committed, so a crash cannot
  apply a reward twice.
- Model version is stored on every recommendation and every bandit state.

## 8. Failure behavior

| Failure | Response |
|---|---|
| Retriever returns nothing | fall back to popular courses (past-window) |
| LinUCB artifact missing | cold-start: uniform scores + exploration |
| Non-finite score | log, exclude candidate, continue |
| DB down | 503, no partial writes |

## 9. Extension points (documented, not built)

- Natural-language profile extraction (optional LLM service) that fills the same
  `users` fields — the rest of the system would not change.
- Per-segment bandits once traffic justifies them.
- ANN retrieval (FAISS) if the catalogue grows past tens of thousands.
- A/B testing framework for online policy comparison.

None of these are implemented now; they are listed so the design is not closed.
