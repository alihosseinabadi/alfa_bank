"""Сборка общего каталога образовательных материалов."""

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.data_preparation.materials import build_material_catalog


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=ROOT / "data" / "interim",
    )
    args = parser.parse_args()

    catalog = build_material_catalog(args.input_dir)

    output = args.input_dir / "materials_enriched.jsonl"

    catalog.to_json(
        output,
        orient="records",
        lines=True,
        force_ascii=False,
    )

    print(f"Всего материалов: {len(catalog)}")
    print(f"Уникальных ключей: {catalog['item_key'].nunique()}")
    print(f"Файл сохранён: {output}")

    print("\nТипы материалов:")
    print(catalog["item_type"].value_counts().to_string())

    print("\nТипы доступа:")
    print(catalog["access_type"].value_counts().to_string())

    print("\nЗаполненность характеристик:")
    for column in ["topics", "tags", "industry_labels"]:
        count = catalog[column].map(bool).sum()
        print(f"{column}: {count} из {len(catalog)}")

    print(
        "\nБез даты публикации:",
        catalog["published_at"].isna().sum(),
    )


if __name__ == "__main__":
    main()
