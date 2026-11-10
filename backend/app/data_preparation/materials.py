"""Единый каталог исходных материалов без фильтрации."""

from pathlib import Path

import pandas as pd

from .catalog import read_raw, attach_labels


# EntityTypeId взяты из предоставленной базы.
# Они позволяют учитывать одновременно ID и тип материала.
SOURCES = [
    (
        "courses_raw.csv", "course",
        "8b440b1a-00c3-423a-9bae-3376475eb203",
    ),
    (
        "articles_raw.csv", "article",
        "8ede4179-0faf-407d-a4fc-1d94f9a63089",
    ),
    (
        "documents_raw.csv", "document",
        "da1ad865-8605-4ab1-9f6c-4489a26fbc35",
    ),
    (
        "webinars_raw.csv", "webinar",
        "ece4acf3-5dd3-47b9-9f08-99c0d6203cc7",
    ),
    (
        "podcasts_raw.csv", "podcast",
        "142c23e2-bf71-4a73-b12e-6b1b5e4d47cc",
    ),
]

FIELDS = {
    "Id": "item_id",
    "Title": "title",
    "Description": "description",
    "DescriptionAdditional": "description_additional",
    "DescriptionExt": "description_extra",
    "CardDescription": "card_description",
    "Target": "target",
    "Duration": "duration_raw",
    "Cost": "price_raw",
    "Published": "source_published_at",
    "StatusId": "source_status_id",
    "TypeId": "source_type_id",
    "IsDeleted": "source_is_deleted",
    "IsClosed": "is_closed_raw",
    "IsPublic": "is_public_raw",
    "HasTrial": "has_trial_raw",
    "Url": "url",
    "StartsAt": "starts_at",
    "EndsAt": "ends_at",
    "Extension": "extension",
    "Size": "file_size_raw",
    "LessonQuantity": "lesson_count_raw",
}


def build_material_catalog(input_dir: Path) -> pd.DataFrame:
    frames = []

    for filename, item_type, entity_type_id in SOURCES:
        frame = read_raw(input_dir, filename).rename(columns=FIELDS)

        if frame["item_id"].isna().any() or frame["item_id"].duplicated().any():
            raise ValueError(f"{item_type}: пустые или повторяющиеся ID")

        frame["item_type"] = item_type
        frame["entity_type_id"] = entity_type_id
        frames.append(frame)

    catalog = pd.concat(frames, ignore_index=True)
    expected_count = len(catalog)

    catalog["item_key"] = (
        catalog["item_type"] + ":" + catalog["item_id"]
    )

    if catalog["item_key"].duplicated().any():
        raise ValueError("Повторяющиеся ключи материалов")

    settings = read_raw(
        input_dir, "content_settings_raw.csv"
    ).rename(columns={
        "Id": "ContentSettingsId",
        "EntityId": "item_id",
        "EntityTypeId": "entity_type_id",
        "StatusId": "settings_status_id",
        "TypeId": "access_type_id",
        "IsDeleted": "settings_is_deleted",
        "Published": "settings_published_at",
    })

    catalog = catalog.merge(
        settings,
        on=["item_id", "entity_type_id"],
        how="left",
        validate="one_to_one",
    )

    if catalog["ContentSettingsId"].isna().any():
        raise ValueError(
            "Для части материалов не найден ContentSettings"
        )

    for filename, key, label in [
        ("statuses_raw.csv", "source_status_id", "status_title"),
        ("statuses_raw.csv", "settings_status_id", "settings_status_title"),
        ("course_types_raw.csv", "access_type_id", "access_type"),
    ]:
        lookup = read_raw(input_dir, filename)[["Id", "Title"]]
        lookup = lookup.rename(columns={"Id": key, "Title": label})

        catalog = catalog.merge(
            lookup,
            on=key,
            how="left",
            validate="many_to_one",
        )

        if catalog[label].isna().any():
            raise ValueError(f"Не удалось расшифровать {key}")

    relations = [
        (
            "content_settings_topics_raw.csv",
            "topics_raw.csv",
            "TopicId", "topic_ids", "topics",
        ),
        (
            "content_settings_tags_raw.csv",
            "tags_raw.csv",
            "TagId", "tag_ids", "tags",
        ),
        (
            "content_settings_industries_raw.csv",
            "industries_raw.csv",
            "IndustryId", "industry_ids", "industry_labels",
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

    catalog["published_at"] = catalog["source_published_at"].fillna(
        catalog["settings_published_at"]
    )

    catalog["source"] = "organizer_backup"

    if (
        len(catalog) != expected_count
        or catalog["item_key"].duplicated().any()
    ):
        raise ValueError(
            "При объединении потерялись или размножились материалы"
        )

    return catalog.sort_values(
        ["item_type", "item_id"]
    ).reset_index(drop=True)
