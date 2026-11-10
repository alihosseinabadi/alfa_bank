# Alfa-Kurs — Adaptive Learning Recommendation Engine

Hackathon project for the **Alfa-Bank Web/AI hackathon**, track
**"Personalization of education for entrepreneurs."**

We build one thing and build it well: an **adaptive course recommendation engine**
for Alfa-Kurs that learns from real interaction signals (impressions, clicks,
free-material inspections, purchases) and improves what it recommends over time.

We deliberately did **not** build the Telegram AI assistant. That is a different
product with a different success metric. Our metric is recommendation quality and
conversion.

---

## 1. The problem

Entrepreneurs arrive at Alfa-Kurs with different businesses, stages, budgets and
goals. A single "popular courses" list is a poor fit for all of them:

- A first-time founder needs fundamentals (unit economics, first sales).
- A scaling founder needs operations, hiring and finance.
- A marketing-heavy founder needs distribution, not basic accounting.

A static catalogue forces the user to search. A personalized engine removes that
work and increases the chance the user finds a course worth paying for.

## 2. The product

An adaptive recommendation system with two connected environments:

1. **User application** — onboarding, personalized feed, purchase actions.
2. **Experiment environment** — offline simulation that proves the algorithm
   beats baselines under identical conditions.

```
Profile  ->  Retrieval (top-50)  ->  LinUCB ranking  ->  Recommendations
                                        ^                     |
                                        |                     v
                                  Reward update  <-  Impressions / clicks /
                                                      inspections / purchases
```

Every recommendation is logged as an *impression*. Every user action is logged as
an *interaction* with a reward. The bandit updates from those rewards, so the feed
improves with use.

## 3. Algorithm in one paragraph

For a user, we build a **context vector** `x` from user features (industry, stage,
experience, interests, goals), course features (category, difficulty, price,
duration, free material) and context features (hour, device, session depth).
Candidate courses come from **content-based retrieval** (TF-IDF or sentence
embeddings, cosine similarity, top 50). A **LinUCB contextual bandit** scores each
candidate as `score = theta^T x + alpha * sqrt(x^T A^-1 x)`. The first term is
exploitation (what we believe works), the second is exploration (where we are
uncertain). After the user acts, the model updates `A` and `b`. This is documented
in depth in [`docs/linucb_explained.md`](docs/linucb_explained.md).

## 4. Technology stack

| Layer | Choice | Why |
|---|---|---|
| Backend | Python, FastAPI, Pydantic | Typed, fast to build, auto docs |
| Database | PostgreSQL + SQLAlchemy + Alembic | Real relational model + migrations |
| ML | NumPy, Pandas, Scikit-learn | Enough for TF-IDF, features, LinUCB |
| Embeddings | sentence-transformers | Optional semantic retrieval comparison |
| Experiments | Python scripts + Matplotlib | Reproducible offline evaluation |
| Frontend | React, TypeScript, Vite, Tailwind, Recharts | Fast UI, readable analytics |
| Local infra | Docker Compose | One command to run DB + API + UI |

No LLM in the core loop. No microservices. No FAISS at this dataset size.

## 5. Repository map

```
alfa-kurs/
├── README.md                  # you are here
├── ARCHITECTURE.md            # how all components connect
├── DEVELOPMENT_GUIDE.md       # how to build it, step by step
├── PROJECT_ROADMAP.md         # priorities and milestones
├── docker-compose.yml         # local PostgreSQL + services
├── .env.example               # every required environment variable
├── .gitignore
├── docs/                      # deep-dive documentation
├── backend/                   # FastAPI app, ML modules, tests
├── frontend/                  # React application
├── experiments/               # offline simulation + evaluation
├── data/                      # course catalogue + synthetic data
└── scripts/                   # seed + experiment entry points
```

Each directory has its own `README.md` that explains what it contains, what each
planned file is responsible for, what imports it, how to test it, and what to
learn to understand it.

## 6. Current status

This repository currently contains the **architecture, documentation and
scaffolding** layer. Source implementations are added phase by phase following
[`PROJECT_ROADMAP.md`](PROJECT_ROADMAP.md). Nothing here pretends to be finished.

Planned phases:

| Phase | Deliverable |
|---|---|
| 0 | Architecture + docs (this commit) |
| 1 | Repository foundation, config, Docker |
| 2 | ML foundation: data, simulator, retrieval, LinUCB, rewards |
| 3 | Experiments + baselines + metrics + plots |
| 4 | Backend: database, API, service integration |
| 5 | Frontend: onboarding, feed, analytics |
| 6 | Integration, tests, demo, presentation |

## 7. How the hackathon demo will work

1. Judge fills an onboarding form as an entrepreneur.
2. The feed returns personalized courses, each with a visible reason.
3. Judge clicks / inspects / buys a course; the UI records interactions.
4. Open the analytics screen: LinUCB vs Random vs Top Popular over N simulated
   users — cumulative reward, regret, CTR, conversion, NDCG@K.

## 8. Honesty statement

All conversion and reward numbers shown in the experiment environment are from a
 **synthetic user simulator**, not from real Alfa-Kurs traffic. We report them as
simulated results and never present them as production outcomes. The simulator
exists so the algorithm can be tested reproducibly and compared fairly against
baselines.

## 9. Documentation index

- [ARCHITECTURE.md](ARCHITECTURE.md) — components, boundaries, data flow
- [DEVELOPMENT_GUIDE.md](DEVELOPMENT_GUIDE.md) — step-by-step build and testing
- [PROJECT_ROADMAP.md](PROJECT_ROADMAP.md) — phases, risks, priorities
- [docs/system_design.md](docs/system_design.md) — end-to-end system design
- [docs/ml_architecture.md](docs/ml_architecture.md) — retrieval, bandit, rewards
- [docs/linucb_explained.md](docs/linucb_explained.md) — the math, line by line
- [docs/reward_design.md](docs/reward_design.md) — two-level reward model
- [docs/database_design.md](docs/database_design.md) — tables, indexes, ERD
- [docs/api_documentation.md](docs/api_documentation.md) — every endpoint
- [docs/evaluation_methodology.md](docs/evaluation_methodology.md) — metrics and fairness
- [docs/presentation_guide.md](docs/presentation_guide.md) — demo script for judges

## 10. What you will learn building this

- How a recommender is actually assembled: retrieval, ranking, feedback loop.
- How contextual bandits differ from classic supervised learning.
- How to design rewards that do not corrupt the learning signal.
- How to evaluate a recommender honestly with baselines and confidence intervals.
- How to ship an ML system as a typed API with a real database and a UI.
