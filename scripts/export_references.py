"""Выгрузка справочников и связей образовательных материалов."""

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.data_preparation.source import read_source_table


OUTPUT_FILES = {
    "ContentSettings": "content_settings_raw.csv",
    "ContentSettingsTopics": "content_settings_topics_raw.csv",
    "ContentSettingsTags": "content_settings_tags_raw.csv",
    "ContentSettingsIndustries": "content_settings_industries_raw.csv",
    "Topics": "topics_raw.csv",
    "Tags": "tags_raw.csv",
    "Industries": "industries_raw.csv",
    "Statuses": "statuses_raw.csv",
    "CourseTypes": "course_types_raw.csv",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compose-file", type=Path, required=True)
    args = parser.parse_args()

    output_dir = ROOT / "data" / "interim"
    output_dir.mkdir(parents=True, exist_ok=True)

    for table_name, filename in OUTPUT_FILES.items():
        frame = read_source_table(table_name, args.compose_file)

        # У справочников проверяем собственный идентификатор.
        # У таблиц связей поля Id нет.
        if "Id" in frame.columns:
            if frame["Id"].isna().any():
                raise ValueError(f"{table_name}: обнаружен пустой Id")

            if frame["Id"].duplicated().any():
                raise ValueError(f"{table_name}: обнаружен повторный Id")

        output = output_dir / filename
        frame.to_csv(output, index=False, encoding="utf-8-sig")

        print(
            f"{table_name}: "
            f"{len(frame)} строк, "
            f"{len(frame.columns)} столбцов → {filename}"
        )

    print("\nВыгрузка справочников завершена.")


if __name__ == "__main__":
    main()
