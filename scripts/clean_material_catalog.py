"""Очистка общего каталога и сохранение отчёта."""

import json
from collections import Counter
from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.data_preparation.cleaning import clean_material_catalog


def main() -> None:
    input_dir = ROOT / "data" / "interim"
    input_file = input_dir / "materials_enriched.jsonl"

    frame = pd.read_json(
        input_file,
        lines=True,
        convert_dates=False,
    )

    catalog = clean_material_catalog(frame, input_dir)
    available = catalog[catalog["is_recommendable"]].copy()

    output_dir = ROOT / "data" / "processed"
    output_dir.mkdir(parents=True, exist_ok=True)

    for filename, data in [
        ("materials_clean.jsonl", catalog),
        ("materials_available.jsonl", available),
    ]:
        data.to_json(
            output_dir / filename,
            orient="records",
            lines=True,
            force_ascii=False,
        )

    reasons = Counter(
        reason
        for values in catalog["exclusion_reasons"]
        for reason in values
    )

    report = {
        "total": len(catalog),
        "recommendable": len(available),
        "excluded": len(catalog) - len(available),
        "recommendable_by_type": {
            key: int(value)
            for key, value in available["item_type"].value_counts().items()
        },
        "missing_duration": int(catalog["duration_is_missing"].sum()),
        "missing_price": int(catalog["price_is_missing"].sum()),
        "exclusion_reasons": dict(reasons),
    }

    report_dir = ROOT / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    report_file = report_dir / "data_cleaning.json"
    report_file.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nКаталоги сохранены: {output_dir}")
    print(f"Отчёт сохранён: {report_file}")


if __name__ == "__main__":
    main()
