"""Выгрузить исходные курсы для дальнейшей подготовки."""

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.data_preparation.source import read_source_table


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--compose-file",
        type=Path,
        required=True,
        help="Путь к compose-файлу существующей исходной базы",
    )
    args = parser.parse_args()

    courses = read_source_table("Courses", args.compose_file)

    if courses.empty:
        raise ValueError("Таблица Courses оказалась пустой")

    if courses["Id"].isna().any():
        raise ValueError("Обнаружены курсы без Id")

    if courses["Id"].duplicated().any():
        raise ValueError("Обнаружены повторяющиеся Id курсов")

    output = ROOT / "data" / "interim" / "courses_raw.csv"
    output.parent.mkdir(parents=True, exist_ok=True)

    courses.to_csv(output, index=False, encoding="utf-8-sig")

    print(f"Количество курсов: {len(courses)}")
    print(f"Количество столбцов: {len(courses.columns)}")
    print(f"Файл сохранён: {output}")

    print("\nПервые пять курсов:")
    print(
        courses[["Title", "Duration", "Cost"]]
        .head()
        .to_string(index=False)
    )

    print("\nКоличество пропусков:")
    print(courses.isna().sum().to_string())


if __name__ == "__main__":
    main()
