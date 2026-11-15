# data/

Datasets used by the API and the experiments.

> **All data in this repository is synthetic or illustrative.** There is no real
> Alfa-Kurs user, course or transaction data here. See
> [`docs/data_provenance.md`](../docs/data_provenance.md) before using anything.

## Folders

| Folder | Contents | Origin |
|---|---|---|
| `courses/` | the course catalogue (`courses.csv`) | hand-written, `source=synthetic` |
| `synthetic/` | generated users and simulation artifacts | `experiments/` simulator |

## Rules

- Data files are text (CSV/JSON/JSONL), reviewable in a diff.
- No personal data, no secrets, no real customer records.
- Generated files are reproducible from a seed and a script.
- Large derived artifacts (embeddings) are not committed.
- Every dataset must state its provenance; `source` is a required column in the catalogue.

## What to learn

Keeping datasets small, versioned and reproducible — and being explicit about what is
real versus synthetic — instead of shipping binary blobs whose origin no one remembers.
