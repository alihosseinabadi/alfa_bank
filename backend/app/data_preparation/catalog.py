"""Объединение исходных курсов со справочниками."""

from pathlib import Path

import pandas as pd


def read_raw(input_dir: Path, filename: str) -> pd.DataFrame:
    return pd.read_csv(
        (input_dir / filename) if (input_dir / filename).exists() else input_dir / _RAW_NAMES.get(filename, filename),
        dtype="string",
        keep_default_na=False,
        na_values=[""],
    )


def attach_labels(
    catalog, links, lookup, foreign_key, ids_column, labels_column
):
    """Добавить списки ID и названий без размножения курсов."""

    links = links[
        links["ContentSettingsId"].isin(catalog["ContentSettingsId"])
    ].copy()

    if links[foreign_key].isna().any():
        raise ValueError(f"{labels_column}: пустой ID в таблице связей")

    links["_order"] = pd.to_numeric(
        links["Order"], errors="coerce"
    ).fillna(0)

    links = links.sort_values(
        ["ContentSettingsId", "_order", foreign_key]
    )
    links = links.drop_duplicates(
        ["ContentSettingsId", foreign_key]
    )

    lookup = lookup[["Id", "Title"]].rename(
        columns={"Id": foreign_key, "Title": "_label"}
    )

    joined = links.merge(
        lookup,
        on=foreign_key,
        how="left",
        validate="many_to_one",
    )

    if joined["_label"].isna().any():
        raise ValueError(
            f"{labels_column}: не найдены названия связанных записей"
        )

    joined["_label"] = joined["_label"].str.strip()

    groups = joined.groupby("ContentSettingsId").agg(
        _ids=(foreign_key, list),
        _labels=("_label", list),
    )

    result = catalog.copy()

    for target, source in [
        (ids_column, "_ids"),
        (labels_column, "_labels"),
    ]:
        result[target] = result["ContentSettingsId"].map(groups[source])
        result[target] = result[target].apply(
            lambda value: value if isinstance(value, list) else []
        )

    return result


def build_course_catalog(input_dir: Path) -> pd.DataFrame:
    courses = read_raw(input_dir, "courses_raw.csv")

    if courses["Id"].isna().any() or courses["Id"].duplicated().any():
        raise ValueError("У курсов пустые или повторяющиеся Id")

    expected_count = len(courses)

    settings = read_raw(input_dir, "content_settings_raw.csv")
    settings = settings[
        settings["EntityId"].isin(courses["Id"])
    ]

    settings = settings[["Id", "EntityId"]].rename(
        columns={"Id": "ContentSettingsId", "EntityId": "Id"}
    )

    catalog = courses.merge(
        settings,
        on="Id",
        how="left",
        validate="one_to_one",
    )

    if catalog["ContentSettingsId"].isna().any():
        raise ValueError(
            "Для части курсов не найдена запись ContentSettings"
        )

    for filename, key, label in [
        ("statuses_raw.csv", "StatusId", "status_title"),
        ("course_types_raw.csv", "TypeId", "access_type"),
    ]:
        lookup = read_raw(input_dir, filename)[["Id", "Title"]]
        lookup = lookup.rename(
            columns={"Id": key, "Title": label}
        )

        catalog = catalog.merge(
            lookup,
            on=key,
            how="left",
            validate="many_to_one",
        )

        if catalog[label].isna().any():
            raise ValueError(f"Не удалось расшифровать поле {key}")

    relations = [
        (
            "content_settings_topics_raw.csv",
            "topics_raw.csv",
            "TopicId",
            "topic_ids",
            "topics",
        ),
        (
            "content_settings_tags_raw.csv",
            "tags_raw.csv",
            "TagId",
            "tag_ids",
            "tags",
        ),
        (
            "content_settings_industries_raw.csv",
            "industries_raw.csv",
            "IndustryId",
            "industry_ids",
            "industry_labels",
        ),
    ]

    for links_file, lookup_file, key, ids_column, labels_column in relations:
        catalog = attach_labels(
            catalog,
            read_raw(input_dir, links_file),
            read_raw(input_dir, lookup_file),
            key,
            ids_column,
            labels_column,
        )

    if len(catalog) != expected_count or catalog["Id"].duplicated().any():
        raise ValueError(
            "При объединении изменилось количество курсов"
        )

    return catalog.sort_values("Id").reset_index(drop=True)

# Read the canonical stage-2 exports without breaking the original CLI filenames.
_RAW_NAMES = {
    "courses_raw.csv": "Courses.csv", "articles_raw.csv": "Articles.csv",
    "documents_raw.csv": "Documents.csv", "webinars_raw.csv": "Webinars.csv",
    "podcasts_raw.csv": "Podcasts.csv", "content_settings_raw.csv": "ContentSettings.csv",
    "content_settings_topics_raw.csv": "ContentSettingsTopics.csv",
    "content_settings_tags_raw.csv": "ContentSettingsTags.csv",
    "content_settings_industries_raw.csv": "ContentSettingsIndustries.csv",
    "topics_raw.csv": "Topics.csv", "tags_raw.csv": "Tags.csv",
    "industries_raw.csv": "Industries.csv", "statuses_raw.csv": "Statuses.csv",
    "course_types_raw.csv": "CourseTypes.csv",
}
