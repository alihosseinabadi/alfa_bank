"""Собрать курсы со связанными темами, тегами и типами доступа."""

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.data_preparation.catalog import build_course_catalog


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=ROOT / "data" / "interim",
    )
    args = parser.parse_args()

    catalog = build_course_catalog(args.input_dir)

    output = args.input_dir / "courses_enriched.jsonl"

    catalog.to_json(
        output,
        orient="records",
        lines=True,
        force_ascii=False,
    )

    print(f"Курсов после объединения: {len(catalog)}")
    print(f"Уникальных Id: {catalog['Id'].nunique()}")
    print(f"Файл сохранён: {output}")

    print("\nСтатусы:")
    print(catalog["status_title"].value_counts().to_string())

    print("\nТипы доступа:")
    print(catalog["access_type"].value_counts().to_string())

    print("\nЗаполненность характеристик:")
    for column in ["topics", "tags", "industry_labels"]:
        count = catalog[column].map(bool).sum()
        print(f"{column}: {count} из {len(catalog)}")


if __name__ == "__main__":
    main()
