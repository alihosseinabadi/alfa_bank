"""Seed the product ``courses`` table from the tracked synthetic catalogue.

The API already exposes ``/api/v1/courses`` and the ML bundle is built from
``data/courses/courses.csv``. This script loads the same rows into PostgreSQL so
the product database is not empty and the catalogue endpoint returns real
(still clearly synthetic) products on a fresh ``docker compose up``.

Idempotent: rows are matched by title + source and updated in place.

Usage:
    python scripts/seed_courses.py --csv data/courses/courses.csv
"""
import argparse
import csv
import json
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.database import product_sessions
from app.models.course import Course

DIFFICULTY = {"beginner": "базовый", "intermediate": "средний", "advanced": "продвинутый"}
CATEGORIES = {"marketing", "sales", "finance", "management", "programming", "entrepreneurship"}


def read_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise SystemExit(f"empty course catalogue: {path}")
    for row in rows:
        difficulty = row["difficulty"].strip()
        if difficulty not in DIFFICULTY:
            raise SystemExit(f"unknown difficulty {difficulty!r} in {row['course_id']}")
        if row["category"].strip() not in CATEGORIES:
            raise SystemExit(f"unknown category {row['category']!r} in {row['course_id']}")
        if float(row["duration_minutes"]) <= 0 or float(row["price"]) < 0:
            raise SystemExit(f"invalid duration/price in {row['course_id']}")
        if not (row["title"].strip() or row["title_ru"].strip()):
            raise SystemExit(f"missing title in {row['course_id']}")
    return rows


def seed(path: Path) -> dict:
    created = updated = 0
    with product_sessions()() as db:
        for row in read_rows(path):
            title = row["title_ru"].strip() or row["title"].strip()
            price = Decimal(row["price"].strip())
            values = {
                "title": title,
                "description": (row.get("description_ru") or row["description"]).strip(),
                "type": "course",
                "price": price,
                "is_free": price == 0,
                "duration_minutes": int(float(row["duration_minutes"])),
                "category": row["category"].strip(),
                "difficulty": DIFFICULTY[row["difficulty"].strip()],
                "source": row["source"].strip(),
            }
            course = (
                db.query(Course)
                .filter(Course.title == title, Course.source == values["source"])
                .one_or_none()
            )
            if course is None:
                db.add(Course(**values))
                created += 1
            else:
                for key, value in values.items():
                    setattr(course, key, value)
                updated += 1
        db.commit()
        total = db.query(Course).count()
    return {"created": created, "updated": updated, "total": total, "csv": str(path)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, default=ROOT / "data/courses/courses.csv")
    print(json.dumps(seed(parser.parse_args().csv), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
