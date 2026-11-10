"""Выгрузка пяти типов образовательных материалов."""

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.data_preparation.source import read_source_table


OUTPUT_FILES = {
    "Courses": "courses_raw.csv",
    "Articles": "articles_raw.csv",
    "Documents": "documents_raw.csv",
    "Webinars": "webinars_raw.csv",
    "Podcasts": "podcasts_raw.csv",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compose-file", type=Path, required=True)
    args = parser.parse_args()

    output_dir = ROOT / "data" / "interim"
    output_dir.mkdir(parents=True, exist_ok=True)

    total = 0

    for table_name, filename in OUTPUT_FILES.items():
        frame = read_source_table(table_name, args.compose_file)

        if frame.empty:
            raise ValueError(f"{table_name}: таблица пустая")

        if frame["Id"].isna().any():
            raise ValueError(f"{table_name}: обнаружен пустой Id")

        if frame["Id"].duplicated().any():
            raise ValueError(f"{table_name}: повторяющиеся Id")

        if frame["Title"].fillna("").str.strip().eq("").any():
            raise ValueError(f"{table_name}: пустое название")

        output = output_dir / filename
        frame.to_csv(output, index=False, encoding="utf-8-sig")

        total += len(frame)

        print(
            f"{table_name}: "
            f"{len(frame)} строк, "
            f"{len(frame.columns)} столбцов → {filename}"
        )

    print(f"\nВсего исходных материалов: {total}")
    print("Выгрузка завершена. Фильтрация пока не выполнялась.")


if __name__ == "__main__":
    main()
