# Onboarding — six questions mapped onto the existing profile

Scope: `backend/app/ml/onboarding.py`, `data/onboarding_goal_topics.json`,
`backend/tests/test_onboarding.py`. Contract version `onboarding-v1`; goal/topic map
version `onboarding-goal-topics-v1`.

Status: **implemented as a pure module and tested; not wired to any API route or UI.**
No user has seen these questions, so no onboarding-related metric below is measured on
real traffic. What *is* measured is the module's behaviour (24 tests) and that the
shipped goal map resolves against the frozen catalogue.

---

## 1. Why a separate layer

The profile schema (`profiles-v1`) already has every field onboarding needs:
`business_stage`, `industry`, `experience`, `budget_preference`,
`available_time_minutes`, `selected_topics`. Adding an onboarding schema would have
created a second source of truth for the same facts, so this module only *translates*
answers into those existing fields. `build_request_context` and everything downstream
keep working unchanged.

## 2. The six questions

| question id | type | profile field it fills | skipped (`None`) means |
|---|---|---|---|
| `business_area` | `trade / services / production / it / food / other` | `industry` (as a Russian label, e.g. `торговля`) | industry stays `None` |
| `stage` | `idea / first_sales / growing / scaling` | `business_stage` | no stage constraint |
| `goal` | 8 goals, see §3 | `selected_topics` (via the goal map) | no topic selection at all |
| `experience` | `beginner / some / experienced` | `experience` | no experience filter |
| `available_time` | `15m / 1h / long` | `available_time_minutes` (`15 / 60 / None`) | no time filter |
| `budget` | `free_only / paid_ok` | `budget_preference` | **no** budget filter — not "free only" |

Every field is optional and `OnboardingAnswers.skipped()` reports exactly which ones
were skipped, so the UI can show "answered 2 of 6" without guessing.

`long` maps to `None` (no upper bound), not to a large number: a large number would
silently exclude long courses from a user who explicitly said they have time.

## 3. Goal → topic map

`data/onboarding_goal_topics.json` is a versioned, hand-written map:

| goal | topics |
|---|---|
| find_customers | Маркетинг, Продажи |
| increase_profit | Юнит-экономика, Финансы |
| retain_customers | Клиентский сервис, Маркетинг |
| build_team | Найм, Операции |
| formalize_business | Право и регистрация, Налоги |
| launch_product | Продукт, Маркетплейсы |
| raise_money | Финансирование, Финансы |
| grow_business | Стратегия, Операции |

Rules enforced in code and tests:

* the file's `version` must equal `GOAL_TOPICS_VERSION`, otherwise `ValueError`;
* there is a test asserting every topic in the shipped map exists in the catalogue's
  `topics` vocabulary (checked against the frozen benchmark catalogue, since the real
  `data/courses/courses.csv` has no `topics` column);
* a goal that maps to nothing (map edited, catalogue changed) yields
  `goal_has_no_catalog_topic` and selects **no** topics — topics are never invented.

## 4. Onboarding is a cold-start aid

`OnboardingPolicy.history_outweighs_after = 3` (interactions). Until the user has three
recorded interactions, the goal topics act as an explicit topic selection. From the
third interaction on, they are dropped from `selected_topics` and the result carries
`history_outweighs_onboarding`; the existing `history_weight` logic in
`request_context.py` then drives the context.

This is deliberate: a topic chosen in a 30-second questionnaire must not outrank
signals from what the user actually opened.

## 5. Never overwrite what the user stated elsewhere

`apply_onboarding(..., base=ExplicitPreferences(...))` merges onboarding *under* an
existing preference set: a field that is already set (settings page, earlier explicit
request) wins, and onboarding only fills `None` / empty values. `selected_topics` are
appended and de-duplicated, never replaced.

## 6. Starter picks

`starter_candidates()` returns up to `starter_limit` (6) deterministic cards for a cold
profile. Ordering: goal-topic overlap descending, then duration ascending, then
`material_key` (stable).

Hard rules:

* `budget=free_only` → materials whose `access_type` is not `Открытый` are excluded;
* `available_time=15m/1h` → materials with a **known** duration above the limit are
  excluded, and materials with an **unknown** duration are also excluded: the card
  would otherwise promise a limit the data cannot back. If that empties the set, the
  function returns `[]` rather than a wrong promise;
* a goal is set → only materials in the goal's topics are eligible;
* each card's `reason` names the answers it came from, and `matched_question` is the
  answer that actually *drove* the pick (a budget note cannot take credit for a
  goal-based card).

## 7. Measured evidence

Behavioural tests (24, all passing):

```
python -m pytest backend/tests/test_onboarding.py -q
```

Covered: skipped answers stay `null`; partial answers leave the rest `null`; goal →
topics with limit; unknown goal → no topics; history rule at 2 vs 3 interactions;
base preferences never overwritten; area/stage/experience/time/budget mapping; `long` →
`None`; invalid interaction counts (`-1`, `1.5`, `True`, `"3"`) rejected; incompatible
onboarding and goal-map versions rejected; missing map → empty map; shipped map names
only catalogue topics; starter determinism, limit, goal/free/time filtering, reason
attribution and the "empty beats wrong" case.

Smoke run of the shipped map against the frozen benchmark catalogue (168 materials),
default policy:

| goal | starters (default) | starters (`free_only` + 15 min) |
|---|---|---|
| find_customers | 6 | 2 |
| increase_profit | 6 | 3 |
| retain_customers | 6 | 3 |
| build_team | 6 | 2 |
| formalize_business | 6 | 2 |
| launch_product | 6 | 3 |
| raise_money | 6 | 4 |
| grow_business | 6 | 2 |

The tight setting is genuinely tight — 2–4 cards, not 6 — because most catalogue
materials are longer than 15 minutes. That is the intended behaviour, and it is the
main risk to conversion: the set can look sparse.

## 8. What is not measured, and known limits

* **No live impact.** No API route serves these questions, so there is no completion
  rate, no drop-off per question and no effect on first-session clicks.
* **The goal map is a hypothesis.** Eight goals × two topics, written by hand, never
  validated against user language. It should be revisited with real query data before
  launch, and the version string bumped if it changes.
* **`business_area` is stored but unused.** There is no industry vocabulary in the
  catalogue, so the label only reaches `RequestContext.industry` for display. Any
  future industry filter must not treat absence as "no preference" vs "not asked" —
  both are `None` today. That ambiguity is inherited from `profiles-v1`, not created
  here.
* **No onboarding events.** Completion is not recorded anywhere; `event_service.py`
  was left untouched. Without an event, the questions cannot be A/B tested at all.
* **Starter set is not personalised beyond the answers.** No popularity, no quality
  score, no difficulty match — only goal topics, budget, time and duration.

## 9. Wiring it up later (not done here)

1. Add an API route that accepts `OnboardingAnswers`, calls `apply_onboarding` and
   stores the resulting `ExplicitPreferences` through the existing settings path.
2. Call `starter_candidates` on the cold profile, passing catalogue rows adapted to
   the `MaterialLike` protocol (five fields).
3. Emit an onboarding-completion event *before* measuring anything; without it there
   is no denominator.
4. Bump `GOAL_TOPICS_VERSION` when the map changes; `apply_onboarding` rejects unknown
   versions on load, and old stored answers stay readable because the answers schema is
   separate (`onboarding-v1`).

## 10. Reproduction

```
python -m pytest backend/tests/test_onboarding.py -q
python -c "from app.ml.onboarding import load_goal_topics; print(load_goal_topics())"
```

Run from the repository root with `PYTHONUTF8=1` on Windows.
