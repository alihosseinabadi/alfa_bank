# Reward Design

How user behavior becomes a learning signal — and how we prevent corruption.

---

## 1. Policy (authoritative)

| Event | Reward | Stored as |
|---|---|---|
| Impression shown, no engagement | **0** | no interaction row; the impression row is the denominator |
| Click | **+1** | interaction row |
| Free-material inspection | **+1** | interaction row |
| Purchase | **+10** | interaction row |

Weights are configurable (`REWARD_CLICK`, `REWARD_INSPECT`, `REWARD_PURCHASE`).
Defaults above express the product goal: purchases matter most.

## 2. Does a purchase replace or supplement earlier engagement?

**It supplements at the event level, and is capped per impression.**

- Every event is its own row with its own reward. A click that happened earlier
  keeps its +1; the purchase adds +10.
- At most **one of each event type per impression** is allowed (unique constraint on
  `(impression_id, event_type)`). So a single impression can contribute at most
  `1 + 1 + 10 = 12`.
- A purchase is **never expanded** into click/inspect rewards. It is not
  `click + inspect + purchase`; it is exactly one purchase row valued at +10.

Why not "replace"? Replacing would erase the click signal that taught the model the
user was interested at all, and would make the same journey's reward history
inconsistent depending on whether the purchase happened. Supplementing with a cap
keeps history append-only and bounded.

## 3. No double counting: the four guards

1. **Unique `(impression_id, event_type)`** in the database.
2. **Unique `(user_id, course_id, 'purchase')`** — a course is bought once per user.
3. **Service-level idempotency**: repeated POSTs with the same idempotency key return
   the existing row instead of inserting.
4. **Reward computed once** by the reward engine and stored on the row; the bandit
   consumes the stored value, never recomputes it later.

## 4. Attribution of delayed purchases

Purchases can happen after the recommendation. We attribute them with
`interactions.impression_id`.

```
POST /api/interactions/purchase { user_id, course_id, impression_id? }
```

Resolution order in `interaction_service`:

1. If `impression_id` is provided, use it (must belong to the same user and course).
2. Otherwise, take the **most recent impression** for `(user_id, course_id)`.
3. If none exists, or the impression is older than
   `PURCHASE_ATTRIBUTION_DAYS` (default 7), reject with `409`.

The bandit updates using the feature context recorded for that impression and the
`model_version` that produced it. This avoids updating today's model with a vector
from a different feature layout.

## 5. Where the reward is computed

`backend/app/ml/reward_engine.py`:

```python
reward = reward_engine.compute(event_type, weights=settings)
```

- `linucb.py` never decides what a click is worth.
- `interaction_service.py` calls the engine, stores the reward, then updates the bandit.
- Changing weights requires no algorithm changes and no data migration.

## 6. Reward scaling

Rewards are bounded (`0..10`) on purpose:

- `α` is tuned relative to reward magnitude;
- huge rewards make the exploration bonus negligible;
- tiny rewards let noise dominate.

If weights change by an order of magnitude, re-tune `α` and record it in the
experiment manifest.

## 7. Negative signals

No explicit negative reward in the MVP. Absence of interaction is reward 0.
Rationale: ignoring a course may reflect position bias, timing or budget, not
dislike. Explicit negatives need strong evidence to avoid poisoning the policy.

`no_interaction` is therefore **not** a stored event. It is the absence of rows; the
impression row itself still counts in the denominator.

## 8. Tests

`tests/test_rewards.py` asserts:

- click = 1, inspect = 1, purchase = 10, unknown type raises;
- purchase produces exactly one row and is not expanded;
- two clicks on the same impression are rejected (unique constraint);
- a second purchase of the same course by the same user is rejected;
- reward equals the configured weight, not a hardcoded constant.

`tests/test_attribution.py` asserts:

- purchase without impression → 409;
- purchase with an impression older than the window → 409;
- purchase with a valid impression updates the bandit with that impression's context;
- attribution is deterministic.

## 9. Learning signal in one sentence

> A course that is clicked, inspected and bought accumulates 12 reward units in its
> feature direction; LinUCB raises its expected score for similar users — with each
> signal counted exactly once and capped per impression.
