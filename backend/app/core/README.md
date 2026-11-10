# backend/app/core/

Cross-cutting configuration. Nothing here imports domain code.

## Files

| File | Purpose |
|---|---|
| `config.py` | Typed settings loaded from environment (Pydantic BaseSettings) |
| `constants.py` | Event types, default reward weights, algorithm names |
| `logging.py` | Consistent logger setup (planned) |

## config.py should expose

```python
class Settings(BaseSettings):
    database_url: str
    alpha: float = 1.0              # LinUCB exploration
    linucb_ridge: float = 0.01      # keeps A positive definite
    reward_click: float = 1.0
    reward_inspect: float = 1.0
    reward_purchase: float = 10.0
    purchase_attribution_days: int = 7
    retrieval_k: int = 50
    feature_version: str = "v1"
    embedding_model: str = "all-MiniLM-L6-v2"
    model_dir: str = "artifacts"
    class Config: env_file = ".env"
```

## Why central config

- One source of truth for tunables (rewards, alpha, k).
- Experiments and the API read the same values.
- Tests can override settings without patching `os.environ` everywhere.

## Rules

- No `os.environ` calls outside this package.
- Defaults live here, secrets live in `.env` (never committed).
- Anything an experiment wants to vary belongs in settings.

## What to learn

Twelve-factor configuration and why scattering environment reads across a codebase
makes behavior unreproducible.
