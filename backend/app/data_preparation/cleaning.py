"""Очистка каталога и фильтр общей рекомендательной ленты."""

import re
import unicodedata
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

import pandas as pd

from .catalog import read_raw


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag in {"p", "div", "br", "li", "h1", "h2", "h3", "tr"}:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        if tag in {"p", "div", "li", "h1", "h2", "h3", "tr"}:
            self.parts.append(" ")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def clean_text(value) -> str:
    if value is None or pd.isna(value):
        return ""

    parser = TextExtractor()
    parser.feed(str(value))
    parser.close()

    text = unicodedata.normalize(
        "NFKC", unescape("".join(parser.parts))
    )
    return re.sub(r"\s+", " ", text).strip()


def parse_bool(value):
    if value is None or pd.isna(value):
        return None

    text = str(value).strip().lower()

    if text in {"t", "true", "1"}:
        return True
    if text in {"f", "false", "0"}:
        return False

    raise ValueError(f"Неизвестное логическое значение: {value!r}")


def parse_duration(value):
    text = clean_text(value).lower().replace(",", ".")
    text = re.sub(r"[~≈]|\bоколо\b", "", text).strip()

    pattern = (
        r"(\d+(?:\.\d+)?)\s*"
        r"(час(?:а|ов)?|ч|минут(?:а|ы)?|мин)\b\.?"
    )

    matches = list(re.finditer(pattern, text))

    if not matches or re.sub(pattern, "", text).strip():
        return None

    minutes = sum(
        float(match[1]) * (60 if match[2].startswith("ч") else 1)
        for match in matches
    )

    return minutes if minutes > 0 else None


def clean_material_catalog(
    frame: pd.DataFrame,
    input_dir: Path,
) -> pd.DataFrame:
    result = frame.copy()

    if (
        result["item_key"].isna().any()
        or result["item_key"].duplicated().any()
    ):
        raise ValueError("Пустые или повторяющиеся ключи материалов")

    text_fields = [
        "title", "description", "description_additional",
        "description_extra", "card_description", "target",
    ]

    for field in text_fields:
        result[field + "_clean"] = result[field].map(clean_text)

    for filename, ids_field, labels_field in [
        ("topics_raw.csv", "topic_ids", "topics"),
        ("tags_raw.csv", "tag_ids", "tags"),
        ("industries_raw.csv", "industry_ids", "industry_labels"),
    ]:
        lookup = read_raw(input_dir, filename).set_index(
            "Id", verify_integrity=True
        )

        id_lists, label_lists = [], []

        for ids in result[ids_field]:
            if not isinstance(ids, list):
                raise ValueError(f"{ids_field}: ожидался список")

            kept_ids, labels = [], []

            for value in ids:
                if value not in lookup.index:
                    raise ValueError(f"{ids_field}: неизвестный ID")

                row = lookup.loc[value]

                if parse_bool(row["IsDeleted"]) is True:
                    continue

                label = clean_text(row["Title"])

                if not label:
                    raise ValueError(f"{labels_field}: пустая метка")

                kept_ids.append(value)
                labels.append(label)

            id_lists.append(kept_ids)
            label_lists.append(labels)

        result[ids_field] = id_lists
        result[labels_field] = label_lists

    result["duration_minutes"] = pd.to_numeric(
        result["duration_raw"].map(parse_duration),
        errors="coerce",
    )
    result["duration_is_missing"] = result["duration_minutes"].isna()
    result["duration_is_approximate"] = (
        result["duration_raw"].fillna("").str.contains(
            r"[~≈]|около", case=False, regex=True
        )
    )

    result["price"] = pd.to_numeric(
        result["price_raw"], errors="coerce"
    )

    if result["price"].lt(0).any():
        raise ValueError("Отрицательная цена")

    result["price_is_missing"] = result["price"].isna()
    result["is_free"] = result["access_type"].eq("Открытый")

    exclusions = []

    for row in result.to_dict("records"):
        reasons = []

        if (
            parse_bool(row["source_is_deleted"]) is True
            or parse_bool(row["settings_is_deleted"]) is True
        ):
            reasons.append("deleted")

        if (
            row["status_title"] != "Опубликовано"
            or row["settings_status_title"] != "Опубликовано"
        ):
            reasons.append("not_published")

        if parse_bool(row["is_closed_raw"]) is True:
            reasons.append("closed")

        if (
            row["item_type"] == "article"
            and parse_bool(row["is_public_raw"]) is not True
        ):
            reasons.append("not_public")

        if row["access_type"] not in {
            "Открытый", "Платный", "По подписке"
        }:
            reasons.append("unsupported_access")

        if not clean_text(row["url"]):
            reasons.append("missing_url")

        if not row["title_clean"]:
            reasons.append("missing_title")

        exclusions.append(reasons)

    result["exclusion_reasons"] = exclusions
    result["is_recommendable"] = result["exclusion_reasons"].map(
        lambda reasons: not reasons
    )

    result["search_text"] = result.apply(
        lambda row: " ".join(
            [row[field + "_clean"] for field in text_fields]
            + row["topics"]
            + row["tags"]
        ).strip(),
        axis=1,
    )

    if len(result) != len(frame):
        raise ValueError("Изменилось число исходных материалов")

    return result
