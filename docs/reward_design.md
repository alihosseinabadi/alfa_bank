# Reward Design

How user behavior becomes a learning signal — and how we avoid corrupting it.

---

## 1. Principle

One event, one row, one reward. The reward encodes **how strong the intent** was,
not how many things happened.

| Event | Reward | Meaning |
|---|---|---|
| impression | 0 | shown, not an action |
| click | +1 | opened the course |
| inspect | +1 | examined free material |
| purchase | +10 | paid — strongest intent |
| no_interaction | 0 | shown and ignored |

Weights are configurable via settings so experiments can test alternatives, but the
defaults express the product goal: **purchases matter most**, interest matters some.

## 2. Why purchases are not "clicks + inspect + purchase"

A user who buys almost always clicked first. If we awarded click and inspect rewards
*as part of* the purchase, the same behavior would be counted three times and the
model would chase clicks instead of revenue.

Rule: each event is logged independently and exactly once. A purchase emits a
purchase event only. The click that happened earlier is its own row with its own
reward. No retroactive edits.

## 3. Where the reward is computed

`backend/app/ml/reward_engine.py`:

```
reward = reward_engine.compute(event_type, weights=settings)
```

- `linucb.py` never decides what a click is worth.
- `interaction_service.py` calls the engine, then passes the scalar to the bandit.
- Changing weights requires no algorithm changes.

This separation is what lets us run the reward-ablations in `experiments/`.

## 4. Reward scaling

Rewards are on a small bounded scale (`0..10`). This matters because:

- `α` (exploration) is tuned relative to reward magnitude;
- large rewards make the bonus negligible → no exploration;
- tiny rewards make noise dominate.

If weights change by an order of magnitude, re-tune `α` and document it.

## 5. Delayed rewards

Purchases may happen after the recommendation. Two acceptable approaches:

1. **Attribute to the impression** that led to the purchase (a purchase carries the
   `user_id` + `course_id`; we attach it to the most recent impression for that pair).
2. **Time-window attribution** — count a purchase if an impression exists within a
   configured window (e.g. 7 days).

We use (1): simpler, auditable, and each purchase maps to exactly one prior
impression. The chosen impression's stored context is what the bandit updates on.

## 6. Negative signals

For the first version we use **no explicit negative reward**. Absence of interaction
is reward 0. Rationale:

- A user ignoring a course may not dislike it (position bias, timing, budget).
- Explicit negatives need strong evidence to avoid poisoning the policy.

`no_interaction = 0` still teaches the model: it does not raise the expected reward
for that course, so it loses against courses that earn rewards.

## 7. Double-counting test

`tests/test_rewards.py` must assert:

- a purchase produces exactly one interaction row with reward 10;
- no click/inspect rewards are added for the same purchase flow;
- summing an event log equals the sum of individually computed rewards;
- unknown event types raise rather than silently returning 0.

## 8. Learning signal in one sentence

> A course that gets clicked, inspected and bought accumulates a large reward in its
> feature direction; LinUCB raises its expected score for similar users — without any
> of those steps being counted twice.
