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

Every displayed course is logged as a row in `recommendation_impressions` (the
canonical impression record, with `slate_id`, `position`, both scores and the model
version). Every user action is logged as an *interaction* that references that
impression and carries a reward. The bandit updates from those rewards, so the feed
improves with use.

## 3. Algorithm in one paragraph

For a user, we build a **context vector** `x = [user_block | course_block |
interaction_block]`. The interaction block contains `interest[c] × course_category[c]`,
a cosine interest match, an experience–difficulty fit, a goal–skill overlap, and
free-material/price interactions. Candidate courses come from **content-based
retrieval** (TF-IDF or sentence embeddings, cosine similarity, top 50). A **LinUCB
contextual bandit** scores each candidate as
`score = theta^T x + alpha * sqrt(x^T A^-1 x)`. The first term is exploitation, the
second is exploration. After the user acts, the model updates `A` and `b`. One shared
model serves all users; personalization comes from the interaction features, not from
per-user parameters. Full math in [`docs/linucb_explained.md`](docs/linucb_explained.md),
feature contract in [`docs/feature_engineering.md`](docs/feature_engineering.md).

We removed device, hour and session-depth features: there is no reliable data source
for them in this prototype and no measured benefit. The MVP uses observable user and
course features only.

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

No LLM in the core loop. No RAG, no multi-agent, no Telegram bot, no FAISS, no deep
RL, no microservices, no Kafka, no Kubernetes.

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
[`PROJECT_ROADMAP.md`](PROJECT_ROADMAP.md). Nothing here pretends to be finished:
no Python module is described as working until code and tests exist.

Planned phases:

| Phase | Deliverable |
|---|---|
| 0 | Architecture + docs (this commit) |
| 1 | Repository foundation, config, Docker |
| 2 | ML foundation: data, simulator, retrieval, LinUCB, rewards |
| 3 | Experiments + baselines + metrics + plots (≥10 seeds) |
| 4 | Backend: database, API, service integration |
| 5 | Frontend: onboarding, feed, analytics |
| 6 | Integration, tests, demo, presentation |

## 7. How the hackathon demo will work

1. Judge fills an onboarding form as an entrepreneur.
2. The feed returns personalized courses, each with a visible reason.
3. Judge clicks / inspects / buys a course; the UI records interactions against the
   impression that showed the course.
4. Open the analytics screen: LinUCB vs Random vs Top Popular over ≥10 simulated
   seeds — cumulative reward, regret, CTR, free-material inspection rate, purchase
   conversion, NDCG@K, all with confidence intervals.

## 8. Honesty statement

All conversion and reward numbers shown in the experiment environment are from a
**synthetic user simulator**, not from real Alfa-Kurs traffic. The course catalogue
itself is **synthetic/illustrative** — see
[`docs/data_provenance.md`](docs/data_provenance.md). We report simulated results as
simulated and never present them as production outcomes.

## 9. Documentation index

- [ARCHITECTURE.md](ARCHITECTURE.md) — components, boundaries, data flow
- [DEVELOPMENT_GUIDE.md](DEVELOPMENT_GUIDE.md) — step-by-step build and testing
- [PROJECT_ROADMAP.md](PROJECT_ROADMAP.md) — phases, risks, priorities
- [docs/system_design.md](docs/system_design.md) — end-to-end system design
- [docs/ml_architecture.md](docs/ml_architecture.md) — retrieval, bandit, rewards
- [docs/feature_engineering.md](docs/feature_engineering.md) — context vector contract
- [docs/linucb_explained.md](docs/linucb_explained.md) — the math, line by line
- [docs/reward_design.md](docs/reward_design.md) — reward policy and attribution
- [docs/database_design.md](docs/database_design.md) — tables, indexes, ERD
- [docs/api_documentation.md](docs/api_documentation.md) — every endpoint
- [docs/evaluation_methodology.md](docs/evaluation_methodology.md) — metrics and fairness
- [docs/data_provenance.md](docs/data_provenance.md) — what data is real vs synthetic
- [docs/presentation_guide.md](docs/presentation_guide.md) — demo script for judges

## 10. What you will learn building this

- How a recommender is actually assembled: retrieval, ranking, feedback loop.
- How contextual bandits differ from classic supervised learning.
- How to design features that let one shared model personalize.
- How to design rewards that do not corrupt the learning signal.
- How to evaluate a recommender honestly with baselines, seeds and confidence intervals.
- How to ship an ML system as a typed API with a real database and a UI.
