# Presentation Guide

A 5–7 minute demo script for the Alfa-Bank judges. The goal: show a **real,
explainable, evaluated** system — not slides about intentions.

---

## 0. One-sentence pitch

> "Alfa-Kurs recommends the right course to each entrepreneur and gets better every
> time someone clicks, inspects or buys — validated against baselines in a
> reproducible simulation."

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

Say explicitly: *"The impression was logged when the card appeared; that is what
makes CTR and conversion honest."*

## 3. The algorithm (1.5 min)

Keep it to three sentences plus the formula:

> "Retrieval picks the 50 most relevant courses by TF-IDF/embedding similarity.
> LinUCB ranks them with `θᵀx + α√(xᵀA⁻¹x)` — expected reward plus an uncertainty
> bonus. After each interaction we update `A += xxᵀ` and `b += rx`."

If asked "why not a neural net": not enough data, and judges can audit this formula.

## 4. The evidence (2 min)

Open the analytics dashboard:

- Cumulative reward: LinUCB > Popular > Random.
- Cumulative regret: LinUCB lowest and sub-linear.
- CTR and conversion over time.
- Exploration share decaying.
- NDCG@10 across seeds.

Then the honesty line:

> "These are simulated users with hidden preferences, five seeds, mean and confidence
> intervals. We are not claiming production conversion — we are claiming the policy
> learns faster than the baselines under identical conditions."

## 5. Engineering (45s)

- Modular monolith: API -> services -> ML, clean boundaries.
- PostgreSQL with impressions logged at display time.
- Tests for LinUCB stability, reward double-counting, leakage, API contracts.
- Docker Compose from a clean clone.

## 6. Close (20s)

- What is next: real traffic, per-segment policies, NL profile extraction, A/B tests.
- Ask for the thing you want (pilot, mentorship, prize).

---

## Likely judge questions

**"Is this just popularity?"**
No. Popularity is our baseline, and LinUCB beats it in the simulation. We show both.

**"How do you avoid overfitting?"**
Multiple seeds, confidence intervals, separate tuning seeds, and a fixed reward
definition.

**"Where does the LLM fit?"**
It does not, deliberately. The challenge is personalization, not conversation. An
optional NL profile parser is a documented extension.

**"Is the data real?"**
No — synthetic, with a documented simulator. We never present simulated lift as real.

**"Why LinUCB and not deep RL?"**
Data volume, interpretability, and stability. LinUCB is ridge regression plus an
optimism bonus; a judge can verify every term.

**"What happens on a cold start?"**
Identity `A`, zero `b`, so the uncertainty bonus dominates and we explore broadly.

## Demo checklist

- [ ] Services running (`docker compose up`).
- [ ] Seed data loaded.
- [ ] Browser on the onboarding page.
- [ ] Analytics plots pre-generated in case the network plays up.
- [ ] Backup screenshots of every screen.
- [ ] Timer: rehearse to under 7 minutes.
