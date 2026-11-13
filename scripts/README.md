# scripts/

Executable entry points. Thin CLI wrappers over the library code.

## Files

| Script | Purpose |
|---|---|
| `seed_database.py` | load `data/courses/courses.csv` into PostgreSQL |
| `run_experiments.py` | run all policies across seeds, write metrics + plots |
| `train_bandit.py` (planned) | offline warm-start the bandit from logged events |
| `generate_embeddings.py` (planned) | precompute course embeddings |

## run_experiments.py

```bash
python scripts/run_experiments.py \
  --users 200 --rounds 50 --seeds 10 --seed-base 42 \
  --output experiments/outputs
```

Produces:

- console table: mean and 95% CI per policy,
- PNG charts in the output directory,
- `run_manifest.json` with parameters and seed.

## seed_database.py

```bash
python scripts/seed_database.py --csv data/courses/courses.csv
```

Validates the CSV before inserting; aborts on the first invalid row.

## Rules

- Scripts contain argument parsing only; logic lives in `experiments/` or `app/`.
- Every script is idempotent or explicitly refuses to duplicate data.
- No secrets hardcoded; read from `.env`.

## What to learn

Keeping CLIs thin, so the same tested functions are used by scripts, the API and
tests.

## Implemented stage-2 catalog commands

- restore_catalog_source.py: restore the supplied archive into an empty isolated PostgreSQL 17 database.
- export_catalog_sources.py: read catalog/content tables and create a hashed source manifest.
- prepare_catalog_tokenizer.py: explicitly prepare the pinned E5 tokenizer.
- build_catalog_bundle.py: normalize materials, resolve aliases, extract content, chunk and validate.
- check_catalog_urls.py: record bounded URL probes separately from content processing.
- verify_catalog_bundle.py: verify checksums, contracts, scopes and token counts.

Runbook and output contracts: [docs/catalog_stage2.md](../docs/catalog_stage2.md).