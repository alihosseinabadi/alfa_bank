# Presentation Guide

A 5–7 minute demo script for the Alfa-Bank judges. The goal: show a **real,
explainable, evaluated** system — not slides about intentions.

---

## 0. One-sentence pitch

> "Alfa-Kurs recommends the right course to each entrepreneur and gets better every
> time someone clicks, inspects or buys — validated against baselines across ten
> seeds in a reproducible simulation."

## 1. Opening (30s)

- Problem: entrepreneurs see the same catalogue; most content never finds its user.
- We built an adaptive recommender, not a chatbot.
- Two environments: the live feed and the experiment lab that proves it works.

## 2. Live flow (2–3 min)

1. **Onboarding** — fill the form as a marketing founder in growth stage.
2. **Feed** — point out the *reason* on each card ("matches your interest in
   marketing and sales").
3. **Act** — click one course, inspect a free material, buy a course.
4. **Result** — the feed refreshes; the recommendation changes because the policy
   learned from those signals.

Say explicitly: *"The impression was written when the card appeared — with slate id,
position and both scores — so CTR and conversion have honest denominators."*

## 3. The algorithm (1.5 min)

Keep it to three sentences plus the formula:

> "Retrieval picks the 50 most relevant courses by TF-IDF or embedding similarity.
> LinUCB ranks them with `θᵀx + α√(xᵀA⁻¹x)` — expected reward plus an uncertainty
> bonus. After each interaction we update `A += xxᵀ` and `b += rx`."

Then the personalization point:

> "We use one shared model. It still personalizes because the features include
> user×course interactions — interest times category, experience-difficulty fit,
> goal-skill overlap. We removed device, hour and session-depth because we had no
> data source for them and no evidence they help."

If asked "why not a neural net": not enough data, and judges can audit this formula.

## 4. The evidence (2 min)

Open the analytics dashboard:

- Cumulative reward: LinUCB > Popular > Random.
- Cumulative regret: LinUCB lowest and sub-linear.
- **Three separate funnel metrics**: CTR, free-material inspection rate, purchase
  conversion — never blended into one number.
- Exploration share decaying.
- NDCG@10 across 10 seeds.

Then the honesty lines:

> "These are simulated users with hidden preferences, ten seeds, mean and 95%
> confidence intervals. We are not claiming production conversion — we are claiming
> the policy learns faster than the baselines under identical conditions."

> "The course catalogue itself is synthetic and labelled `source=synthetic`. It is not
> real Alfa-Kurs data."

## 5. Engineering (45s)

- Modular monolith: API → services → ML, clean boundaries.
- One canonical `recommendation_impressions` table; every interaction references it.
- Purchase reward supplements earlier events but is capped at 12 per impression and
  deduplicated by a unique constraint.
- Tests for LinUCB stability, reward double-counting, evaluation fairness and leakage.
- Docker Compose from a clean clone.

## 6. Close (20s)

- What is next: real traffic, per-segment policies, NL profile extraction, A/B tests.
- Ask for the thing you want (pilot, mentorship, prize).

---

## Likely judge questions

**"Is this just popularity?"**
No. Popularity is our baseline, and LinUCB beats it in the simulation. We show both.

**"How do you avoid overfitting?"**
Ten seeds, confidence intervals, separate tuning seeds, and a fixed reward definition.

**"Where does the LLM fit?"**
It does not, deliberately. The challenge is personalization, not conversation. An
optional NL profile parser is a documented extension.

**"Is the data real?"**
No — synthetic courses and simulated users, both documented in `data_provenance.md`.
We never present simulated lift as real.

**"Why LinUCB and not deep RL?"**
Data volume, interpretability, and stability. LinUCB is ridge regression plus an
optimism bonus; a judge can verify every term.

**"How do you stop double counting?"**
Unique `(impression_id, event_type)` and unique purchase per user+course; rewards are
computed once and stored. A purchase never expands into click rewards.

**"What happens on a cold start?"**
`A = λI`, `b = 0`, so the uncertainty bonus dominates and we explore broadly.

## Demo checklist

- [ ] Services running (`docker compose up`).
- [ ] Seed data loaded.
- [ ] Browser on the onboarding page.
- [ ] Experiment run with 10 seeds; plots pre-generated in case the network plays up.
- [ ] Backup screenshots of every screen.
- [ ] Timer: rehearse to under 7 minutes.
