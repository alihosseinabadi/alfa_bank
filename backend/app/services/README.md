# backend/app/services/

Business workflows. This is where components are combined and transactions are owned.

## Files

| File | Responsibility | Uses |
|---|---|---|
| `recommendation_service.py` | build features, retrieve, rank, persist recommendations + impressions | `ml/*`, `models/*` |
| `interaction_service.py` | validate event, compute reward, persist, update bandit | `ml/reward_engine`, `ml/linucb`, `models/*` |
| `analytics_service.py` (planned) | aggregate counts, CTR, conversion, comparison | `models/*`, `experiments/metrics` |

## recommendation_service — steps

1. Load user; 404 if missing.
2. Build user feature vector.
3. Retrieve top-50 candidates.
4. Build context vectors and score with LinUCB.
5. Rank, take top-N.
6. Insert recommendation rows + impression rows in one transaction.
7. Return ranked items with reasons.

## interaction_service — steps

1. Validate the event type.
2. Confirm the referenced impression exists.
3. `reward = reward_engine.compute(event_type)`.
4. Insert the interaction row.
5. Apply `linucb.update(context, reward)`.
6. Persist bandit state with a new version.

## Rules

- Services own transactions; routes do not.
- Services may call `ml/` and `models/`; they never build HTTP responses.
- One public function per use case, clearly named.
- No hidden side effects: the docstring states what is written.

## Test

- `test_api.py` exercises these through HTTP.
- Unit tests can call services with a test session.

## What to learn

Where business logic belongs, how to keep transactions atomic, and why the ML layer
stays pure so these flows are easy to reason about.
