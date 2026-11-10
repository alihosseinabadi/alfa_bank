# data/

Datasets used by the API and the experiments.

## Folders

| Folder | Contents |
|---|---|
| `courses/` | the course catalogue |
| `synthetic/` | generated users and simulation artifacts |

## Rules

- Data files are text (CSV/JSON/JSONL), reviewable in a diff.
- No personal data, no secrets, no real customer records.
- Generated files are reproducible from a seed and a script.
- Large derived artifacts (embeddings) are not committed.

## What to learn

Keeping datasets small, versioned and reproducible instead of binary blobs whose
origin no one remembers.
