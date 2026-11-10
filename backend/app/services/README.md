# backend/app/services/

Business workflows. This is where components are combined and transactions are owned.

## Files

| File | Responsibility | Uses |
|---|---|---|
| `recommendation_service.py` | build features, retrieve, rank, write one impression slate | `ml/*`, `models/*` |
| `interaction_service.py` | resolve impression, compute reward, persist, update bandit | `ml/reward_engine`, `ml/linucb`, `models/*` |
| `analytics_service.py` (planned) | aggregate counts, CTR, inspection rate, conversion, comparison | `models/*`, `experiments/metrics` |

## recommendation_service — steps

1. Load user; 404 if missing.
2. Build user feature block.
3. Retrieve top-50 candidates.
4. Build context vectors (`user | course | interaction`) and score with LinUCB.
5. Rank, take top-N.
6. Generate one `slate_id`; insert one `recommendation_impressions` row per item
   (`position`, `retrieval_score`, `bandit_score`, `algorithm`, `model_version`)
   in a single transaction. No separate impressions table exists.
7. Return ranked items with `impression_id` and reasons.

## interaction_service — steps

1. Validate the event type.
2. Resolve the impression: given `impression_id`, else the most recent impression for
   `(user_id, course_id)` within `PURCHASE_ATTRIBUTION_DAYS`. Missing/expired -> 409.
3. `reward = reward_engine.compute(event_type)`.
4. Insert the interaction row with `impression_id`; the unique
   `(impression_id, event_type)` constraint rejects duplicates with 409.
5. Apply `linucb.update(context_of_that_impression, reward)`.
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
