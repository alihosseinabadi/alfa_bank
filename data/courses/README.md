# data/courses/

The Alfa-Kurs course catalogue used by the demo and the experiments.

> **Provenance:** every row is **synthetic / illustrative**. These are not real
> Alfa-Kurs courses, real prices, or real platform data. See
> [`docs/data_provenance.md`](../../docs/data_provenance.md).

## File

| File | Format | Notes |
|---|---|---|
| `courses.csv` | CSV | one row per course, `source=synthetic` |

## Columns

| Column | Type | Required | Notes |
|---|---|---|---|
| `course_id` | string | yes | unique, stable id |
| `title` | string | yes | |
| `description` | string | yes | used for retrieval |
| `title_ru` | string | no | localized title (optional) |
| `category` | string | yes | marketing, sales, finance, management, programming, entrepreneurship |
| `skills` | string | yes | semicolon-separated |
| `objectives` | string | no | semicolon-separated |
| `difficulty` | string | yes | beginner / intermediate / advanced |
| `duration_minutes` | int | yes | > 0 |
| `price` | float | yes | >= 0, illustrative only |
| `has_free_material` | bool | yes | true / false |
| `source` | string | yes | provenance marker; `synthetic` for every current row |

## Validation

Loading must reject:

- missing required fields, including `source`,
- negative price or non-positive duration,
- unknown difficulty or category,
- duplicate `course_id`,
- empty title / description / skills.

Validation lives in `ml/feature_engineering.py` (`load_and_validate_courses`) and is
exercised by `tests/test_data_validation.py`. A failed row aborts the whole load —
partial catalogues produce silent retrieval bugs.

## Why a CSV

Small, portable, diff-friendly, and editable by a non-engineer. At this size a
database import is overkill.

## Retrieval text

The retriever builds its document as:

```
title + description + skills + objectives
```

Keep descriptions informative; retrieval quality depends on them.

## Replacing with real data

If a real catalogue becomes available:

1. keep the same column set (extra columns may be ignored),
2. set `source` to a documented provenance such as `curated:alfa-kurs:2026-11`,
3. update `docs/data_provenance.md` in the same commit.

No code change is required.

## What to learn

Data validation, provenance, and why a clean, well-described catalogue is half of a
content-based recommender.
