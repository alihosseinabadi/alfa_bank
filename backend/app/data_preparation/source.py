"""Чтение исходных таблиц через существующий PostgreSQL в Docker."""

from io import StringIO
from pathlib import Path
import subprocess

import pandas as pd


EXPORT_COLUMNS = {
    "Courses": (
        "Id", "Title", "Description", "DescriptionAdditional",
        "Target", "Duration", "LessonQuantity", "Cost",
        "TypeId", "StatusId", "HasTrial", "IsClosed",
        "IsDeleted", "Published", "Url",
    ),
    "ContentSettings": (
        "Id", "EntityId", "EntityTypeId", "StatusId",
        "TypeId", "IsDeleted", "Published",
    ),
    "ContentSettingsTopics": (
        "ContentSettingsId", "TopicId", "Order",
    ),
    "ContentSettingsTags": (
        "ContentSettingsId", "TagId", "Order",
    ),
    "ContentSettingsIndustries": (
        "ContentSettingsId", "IndustryId", "Order",
    ),
    "Topics": (
        "Id", "Title", "Description", "IsDeleted", "IsPublic",
    ),
    "Tags": (
        "Id", "Title", "IsDeleted",
    ),
    "Industries": (
        "Id", "Title", "IsDeleted",
    ),
    "Statuses": (
        "Id", "Title",
    ),
    "CourseTypes": (
        "Id", "Title", "IsDeleted",
    ),
}


def read_source_table(
    table_name: str,
    compose_file: Path,
) -> pd.DataFrame:
    """Прочитать разрешённую таблицу, не изменяя исходную базу."""

    if table_name not in EXPORT_COLUMNS:
        raise ValueError(f"Таблица не настроена для выгрузки: {table_name}")

    compose_file = compose_file.resolve()

    if not compose_file.is_file():
        raise FileNotFoundError(f"Не найден compose-файл: {compose_file}")

    columns = ", ".join(
        f'"{column}"' for column in EXPORT_COLUMNS[table_name]
    )

    query = (
        f'COPY (SELECT {columns} FROM public."{table_name}" '
        f'ORDER BY {columns}) '
        "TO STDOUT WITH (FORMAT CSV, HEADER TRUE);"
    )

    command = [
        "docker", "compose",
        "-f", str(compose_file),
        "exec", "-T", "db",
        "psql",
        "-X",
        "--quiet",
        "--set=ON_ERROR_STOP=1",
        "--username=alfa_ml",
        "--dbname=alfa_course",
        "--command", query,
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Не удалось прочитать {table_name}:\n{result.stderr.strip()}"
        )

    return pd.read_csv(
        StringIO(result.stdout),
        dtype="string",
        keep_default_na=False,
        na_values=[""],
    )
