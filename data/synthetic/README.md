# data/synthetic/

Artifacts produced by the simulator. Regenerable; not the source of truth.

## Files (generated)

| File | Contents |
|---|---|
| `sim_users.json` | generated users incl. hidden preferences |
| `interaction_logs.jsonl` | simulated events per round |
| `run_manifest.json` | seed, parameters, git commit, timestamp |

## Rules

- Every file is reproducible from `seed` + parameters.
- Hidden preferences live here and in memory only — never in the API database.
- Do not hand-edit generated files; change the simulator and re-run.
- `run_manifest.json` records the exact seed so a result can be audited.

## Regenerate

```bash
python scripts/run_experiments.py --users 200 --rounds 50 --seeds 10 --seed-base 42
```

## Why keep them

Judges and teammates can reproduce any number in the presentation. A result without a
seed and manifest is an anecdote.

## What to learn

Provenance: recording exactly what produced a result is what makes an experiment
believable.
