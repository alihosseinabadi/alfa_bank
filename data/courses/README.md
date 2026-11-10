# data/courses/

The Alfa-Kurs course catalogue.

## File

| File | Format | Notes |
|---|---|---|
| `courses.csv` | CSV | one row per course |

## Columns

| Column | Type | Required | Notes |
|---|---|---|---|
| `course_id` | string | yes | stable id |
| `title` | string | yes | |
| `description` | string | yes | used for retrieval |
| `title_ru` | string | no | localized title (optional) |
| `category` | string | yes | marketing, sales, finance, management, programming, entrepreneurship |
| `skills` | string | yes | semicolon-separated |
| `objectives` | string | no | semicolon-separated |
| `difficulty` | string | yes | beginner / intermediate / advanced |
| `duration_minutes` | int | yes | > 0 |
| `price` | float | yes | >= 0 |
| `has_free_material` | bool | yes | true / false |

## Validation

Loading must reject:

- missing required fields,
- negative price or duration,
- unknown difficulty,
- duplicate `course_id`.

## Why a CSV

Small, portable, diff-friendly, and editable by a non-engineer. At this size a
database import is overkill.

## Retrieval text

The retriever builds its document as:

```
title + description + skills + objectives
```

Keep descriptions informative; retrieval quality depends on them.

## What to learn

Data validation and why a clean, well-described catalogue is half of a content-based
recommender.
