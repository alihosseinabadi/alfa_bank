# LinUCB Explained

A line-by-line explanation of the algorithm we implement in
`backend/app/ml/linucb.py`. Written so you can defend every symbol to a judge.

---

## 1. The problem it solves

We must choose a course for a user, repeatedly, and learn from the reward. We have
**context** (who the user is, what the course is, when it is shown). We want to:

- exploit what we know (show courses that worked),
- explore what we do not know (show uncertain courses to learn).

This is a **contextual bandit**. Unlike supervised learning, we never see the reward
of the courses we did *not* show — that is the core difficulty.

## 2. Notation

| Symbol | Dimension | Meaning |
|---|---|---|
| `x` | `d` | context vector for one (user, course, context) triple |
| `A` | `d × d` | design matrix: accumulates `x xᵀ` per update |
| `b` | `d` | reward-weighted sum: accumulates `r x` per update |
| `θ` | `d` | estimated reward weights, `θ = A⁻¹ b` |
| `α` | scalar | exploration strength (> 0) |
| `r` | scalar | observed reward for the chosen course |

## 3. The model

We assume the expected reward of course `a` in context `x_a` is linear:

```
E[r | x_a] = θᵀ x_a
```

Ridge regression estimate given all past observations `(x_i, r_i)`:

```
θ = (XᵀX + I)⁻¹ Xᵀ r
```

Map to bandit form:

```
A = XᵀX + I        (so A starts as identity → behaves like a ridge prior)
b = Xᵀ r
θ = A⁻¹ b
```

## 4. The score: exploitation + exploration

```
score(a) = θᵀ x_a  +  α √( x_aᵀ A⁻¹ x_a )
           └────┘     └──────────────────┘
          exploit            explore
```

- **Exploit term** `θᵀx_a`: the reward we expect if we are right.
- **Explore term** `α√(xᵀA⁻¹x)`: the width of our uncertainty around that estimate.
  For a direction never seen, `A⁻¹` is large there, so the bonus is large.

`A⁻¹` appears because `A` is the information matrix: more observations → larger `A`
→ smaller `A⁻¹` → smaller bonus. That single mechanism produces "optimism in the
face of uncertainty".

### Why the square root

`xᵀA⁻¹x` is a squared Mahalanobis distance in feature space. The square root puts it
on the same scale as the reward, so `α` has a reward-unit meaning rather than a
squared-reward meaning.

## 5. Selecting an action

```
scores = [θᵀx_a + α√(x_aᵀ A⁻¹ x_a) for a in candidates]
a* = argmax(scores)
```

The candidate set is the top-50 from retrieval, **not** the whole catalogue.

## 6. The update

After observing reward `r` for the chosen context `x`:

```
A ← A + x xᵀ
b ← b + r x
```

Then `θ` is recomputed lazily (or cached and invalidated). Each update is a rank-1
change to `A` — cheap. This is exactly online ridge regression with an uncertainty
bonus.

Do **not** update `A` with unshown courses. No counterfactual rewards exist.

## 7. Numerical stability

Inverting `A` directly each time is fragile. Rules we follow:

1. **Ridge term**: start `A = I·λ` with `λ` small (e.g. `1e-2`) so `A` is always
   positive definite.
2. **Solve, do not invert**: compute `A⁻¹b` with `numpy.linalg.solve`, never
   `numpy.linalg.inv(A) @ b`.
3. **Symmetry**: after `A += x xᵀ`, symmetrize (`A = (A + Aᵀ)/2`) to fight float drift.
4. **Check finiteness**: assert scores are finite; if not, skip the candidate and log.
5. **Condition number**: optionally monitor `np.linalg.cond(A)`; if it explodes,
   increase the ridge term.
6. **Uncertainty term** uses `solve(A, x)` then `x · solve(A, x)`, clamped at 0 before
   the square root (floating point can yield a tiny negative).

## 8. Worked micro-example

Two candidates, `d = 2`, `A = I`, `b = 0`, `α = 1`.

```
x₁ = [1, 0]   → θᵀx₁ = 0 ; bonus = √1 = 1 ; score = 1
x₂ = [0, 1]   → θᵀx₂ = 0 ; bonus = √1 = 1 ; score = 1
```

Tie → first wins (deterministic tie-break, e.g. lower course id). Suppose reward 10:

```
A = I + [[1,0],[0,0]] = [[2,0],[0,1]]
b = 10 * [1,0] = [10, 0]
θ = A⁻¹b = [5, 0]
```

Next round, same contexts:

```
x₁: exploit 5 ; bonus √(1/2) ≈ 0.71 ; score ≈ 5.71
x₂: exploit 0 ; bonus √1   = 1.00 ; score ≈ 1.00
```

Now `x₁` is strongly preferred, but `x₂` is still explored because its bonus never
collapsed. This is the desired behavior.

## 9. What to say to a judge

> "LinUCB is ridge regression plus an optimism bonus. `A` measures how much we know,
> `b` stores reward-weighted features, `θ = A⁻¹b` is our best guess. We add
> `α√(xᵀA⁻¹x)` to reward uncertainty. Updates are rank-1: `A += xxᵀ`, `b += rx`.
> We solve instead of inverting and keep a ridge term so `A` stays positive definite."

That is the entire algorithm. Everything else is plumbing.

## 10. Common mistakes

- Updating the model with rewards for courses never shown (leakage / fantasy data).
- Using raw unnormalized features → one feature dominates.
- Forgetting the ridge term → singular `A` early on.
- Using `inv` instead of `solve` → numerical drift.
- Treating the exploration bonus as a bug and removing it → no learning.
- Tuning `α` on the evaluation data → overfitting the demo.

## 11. Persistence

Save `A`, `b`, `alpha`, `d`, and a `model_version`. Load with a dimension check; if
the artifact does not match the current feature layout, start fresh and log it.
