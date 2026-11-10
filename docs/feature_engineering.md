# Feature Engineering Specification

Single source of truth for the LinUCB context vector. If code and this document
disagree, the code is wrong.

Scope: **observable features only**. Hidden simulator preferences are never inputs.

---

## 1. Context vector layout

For a (user `u`, course `c`) pair at recommendation time:

```
x = [ user_block | course_block | interaction_block ]     # concatenation
```

`K` = number of categories (configurable; 6 in the sample catalogue).

| Block | Dims | Contents |
|---|---|---|
| `user_block` | `2K + 5` | interests, industry prior, experience, stage one-hot, budget sensitivity |
| `course_block` | `K + 5` | category one-hot, difficulty, price, duration, has_free, skills count |
| `interaction_block` | `K + 5` | interest×category, match, exp–diff fit, goal–skill overlap, free pref×free, price×budget |
| **Total `d`** | **`4K + 15`** | `K=6` → `d = 39` |

Order inside each block is fixed and defined in `backend/app/ml/feature_engineering.py`
as `FEATURE_LAYOUT`. Tests assert `len(x) == d` for every candidate.

## 2. Observable inputs

From onboarding (all stated by the user):

| Field | Type | Used as |
|---|---|---|
| `interests` | category → weight in [0,1] | `user_block` (K dims) |
| `industry` | category label | deterministic prior weights (K dims) |
| `business_stage` | idea / launch / growth | one-hot (3 dims) |
| `experience` | none / some / experienced | ordinal (1 dim) |
| `budget_sensitivity` | 0..1 | 1 dim |
| `goals` | list of tags | goal–skill overlap (interaction block) |

From the catalogue:

| Field | Type | Used as |
|---|---|---|
| `category` | label | one-hot (K) |
| `difficulty` | beginner / intermediate / advanced | ordinal (1) |
| `price` | numeric | min-max (1) |
| `duration_minutes` | int | min-max (1) |
| `has_free_material` | bool | binary (1) |
| `skills` | list | count normalized (1) + overlap (interaction) |

**Not used:** device, hour, session depth, referral source — removed. There is no
concrete data source for them in this prototype and no measured justification.

**Never used:** `hidden_preferences`, simulator oracle values, or anything only the
simulator can see.

## 3. Encoding rules

| Kind | Rule |
|---|---|
| Category | one-hot, fixed category order from config |
| Business stage | one-hot (3) |
| Difficulty | `beginner=0.0`, `intermediate=0.5`, `advanced=1.0` |
| Experience | `none=0.0`, `some=0.5`, `experienced=1.0` |
| Boolean | `0.0` / `1.0` |
| List counts | `min(count / max_count, 1.0)` |

Category order is a constant list, not `set()` order — dictionaries must be
deterministic across processes.

## 4. Normalization rules

All numeric values end as `float32` in `[0, 1]`.

```
minmax(x) = clip((x - min) / (max - min), 0, 1)      # max > min else 0.0
ordinal_difficulty ∈ {0, 0.5, 1}
ordinal_experience ∈ {0, 0.5, 1}
```

Rules:

- Min/max are fitted on the **training catalogue** and stored in the model artifact
  (`feature_stats`). Serving reuses them; it never re-fits per request.
- Vector is clipped once at the end to guard float drift.
- `float32` keeps the artifact small and matches NumPy defaults.

Why normalize: LinUCB's dot product `θᵀx` would otherwise be dominated by raw price
or duration. `[0,1]` keeps every feature comparable and makes `α` interpretable.

## 5. Interaction features (the personalization core)

| Feature | Formula | Why |
|---|---|---|
| `interest_x_category[k]` | `interest[k] * course_onehot[k]` | lets the model learn "this user + this category" jointly, not separately |
| `interest_match` | `cosine(interest_vector, course_category_profile)` | one scalar summary of fit |
| `exp_diff_fit` | `1 - abs(exp_ordinal - diff_ordinal)` | avoids recommending advanced courses to beginners |
| `goal_skill_overlap` | `len(goals ∩ course.skills) / max(len(goals),1)` | objective alignment |
| `free_pref_x_free` | `budget_sensitivity * has_free` | price-sensitive users value free material |
| `price_x_budget` | `price_norm * (1 - budget_sensitivity)` | expensive courses should not surface for budget-sensitive users |

The `interest_x_category` block is a **Hadamard product**, not a duplicate of the
one-hot. It is the term that makes a *shared* LinUCB model personalize: the same
weights act differently per user because this block differs per user.

## 6. Shared model justification

One LinUCB model is trained across all users. Personalization comes from the context
vector, not from per-user parameters. Rationale:

- data volume per user is too small for per-user models;
- a shared model learns category/difficulty/price effects faster;
- the interaction block supplies user-specific signal.

Per-segment models are a documented future step, not part of this MVP.

## 7. Worked example (K = 6, category index: marketing=0)

User: marketing interest 0.9, sales 0.7, others 0; growth stage; some experience;
budget sensitivity 0.8; goals {increase revenue}.

Course: marketing, beginner, price 0.4 (normalized), duration 0.3, free material,
skills {positioning, outreach}.

```
interest_x_category     = [0.9, 0.0, 0.0, 0.0, 0.0, 0.0]
interest_match          ≈ 0.79        # cosine with the marketing-heavy profile
exp_diff_fit            = 1 - |0.5 - 0.0| = 0.5
goal_skill_overlap      = 0/1 = 0.0   # "increase revenue" not in skills
free_pref_x_free        = 0.8 * 1 = 0.8
price_x_budget          = 0.4 * (1-0.8) = 0.08
```

A finance course for the same user would produce a near-zero
`interest_x_category` block and a lower `interest_match`, so it scores lower even
before the uncertainty bonus.

## 8. Validation checklist

- [ ] `len(x) == d` for every candidate.
- [ ] `np.isfinite(x).all()`.
- [ ] `0 <= x <= 1` for every element.
- [ ] Feature order identical between training artifact and serving.
- [ ] Hidden preferences cannot be reached from the feature builder (import test).
- [ ] Missing optional profile fields default deterministically (documented in code).

## 9. Change procedure

Changing this layout is a **breaking change**:

1. Bump `FEATURE_VERSION`.
2. Retrain or reset the bandit artifact (old `A` has the wrong dimension).
3. Update tests and this document in the same commit.
