"""Build a traceable stage-2 bundle from the verified organizer table exports."""
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
import pandas as pd
from .catalog import read_raw
from .materials import build_material_catalog, SOURCES
from .cleaning import clean_material_catalog, parse_bool, parse_duration
from .contracts import Material, SourceIdentity, ContentBlock, ChildLink
from .content import extract_text, block_text
from .eligibility import material_url
from .entity_resolution import build_aliases, resolve_calculator_pages
from .chunking import digest
from .file_text import extract_local_file

MAIN_TABLES = dict(zip([x[1] for x in SOURCES], ["Courses", "Articles", "Documents", "Webinars", "Podcasts"]))
TEXT_FIELDS = ["description", "description_additional", "description_extra", "card_description", "target"]
BODY_SOURCES = [("ArticleEmbedItems", "ArticleId", "Articles"), ("DocumentEmbedItems", "DocumentId", "Documents"),
                ("GlossaryEmbedItems", "GlossaryId", "Glossary"), ("CalculatorPageEmbedItems", "CalculatorPageId", "CalculatorPages")]

def table(input_dir: Path, name: str) -> list[dict]:
    return pd.read_csv(input_dir / (name + ".csv"), dtype="string", keep_default_na=False).to_dict("records")

def text(value) -> str:
    return "" if value is None or pd.isna(value) else str(value)

def integer(value, default=0) -> int:
    return int(value) if text(value) else default

def load_manifest(input_dir: Path) -> dict:
    manifest = json.loads((input_dir / "source_manifest.json").read_text())
    for entry in manifest["files"].values():
        path = input_dir / entry["filename"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError(f"Source checksum mismatch: {path.name}")
    if hashlib.sha256(json.dumps(manifest["files"], sort_keys=True).encode()).hexdigest() != manifest["snapshot_id"]:
        raise ValueError("Invalid source manifest")
    return manifest

def build_catalog(input_dir: Path, document_dir: Path | None = None):
    manifest = load_manifest(input_dir)
    base = clean_material_catalog(build_material_catalog(input_dir), input_dir)
    materials = []
    for row in base.to_dict("records"):
        kind = row["item_type"]
        raw_price = text(row["price_raw"])
        listed_price = float(row["price"]) if not pd.isna(row["price"]) else None
        price_rule = "source_numeric" if listed_price is not None else "unknown"
        if kind == "course" and not raw_price:
            listed_price, price_rule = 0.0, "Courses.Cost:null_means_free_listed_price"
        material = Material(material_key=row["item_key"], item_type=kind,
            source_identities=[SourceIdentity(table=MAIN_TABLES[kind], record_id=row["item_id"])],
            title=row["title_clean"], descriptions=list(dict.fromkeys(row[x + "_clean"] for x in TEXT_FIELDS if row[x + "_clean"])),
            url=material_url(text(row["url"]), kind), topics=row["topics"], tags=row["tags"], industry_labels=row["industry_labels"],
            access_type=text(row["access_type"]), listed_price=listed_price, price_is_missing=not raw_price, price_rule=price_rule,
            duration_minutes=None if pd.isna(row["duration_minutes"]) else row["duration_minutes"],
            published_at=text(row["published_at"]) or None, publication_status=text(row["status_title"]),
            source_entity_type_id=row["entity_type_id"], exclusion_reasons=list(row["exclusion_reasons"]),
            is_discoverable=bool(row["is_recommendable"]), snapshot_id=manifest["snapshot_id"], extracted_at=manifest["extracted_at"],
            raw={key: text(row.get(key)) for key in ["url", "price_raw", "duration_raw", "source_status_id", "source_type_id",
                 "settings_status_id", "access_type_id", "source_is_deleted", "settings_is_deleted", "is_closed_raw", "is_public_raw"]})
        if material.url == "" and "missing_url" not in material.exclusion_reasons:
            material.exclusion_reasons.append("invalid_url")
            material.is_discoverable = False
        if kind in {"webinar", "podcast"}:
            material.quality_flags.append("no_supplied_transcript")
        materials.append(material)

    status = {x["Id"]: x["Title"] for x in table(input_dir, "Statuses")}
    pairs, unmatched = resolve_calculator_pages(table(input_dir, "Calculators"), table(input_dir, "CalculatorPages"))
    aux = [(None, row, "glossary", "Glossary") for row in table(input_dir, "Glossary")]
    aux += [(calc, page, "calculator", "CalculatorPages") for calc, page in pairs]
    aux += [(None, calc, "calculator", "Calculators") for calc in unmatched]
    for calc, row, kind, source_table in aux:
        published = status.get(row.get("StatusId"), "unknown")
        reasons = []
        if parse_bool(row["IsDeleted"]) is True or (calc and parse_bool(calc["IsDeleted"]) is True):
            reasons.append("deleted")
        if published != "Опубликовано":
            reasons.append("not_published")
        title = extract_text(row["Title"])
        url = material_url(row["Url"], kind)
        if not title:
            reasons.append("missing_title")
        if not url:
            reasons.append("missing_url")
        identities = [SourceIdentity(table=source_table, record_id=row["Id"])]
        if calc:
            identities.append(SourceIdentity(table="Calculators", record_id=calc["Id"]))
        materials.append(Material(material_key=f"{kind}:{calc['Id'] if calc else row['Id']}", item_type=kind,
            source_identities=identities, title=title, descriptions=[extract_text(row["Description"])] if row["Description"] else [],
            url=url, access_type="Открытый", duration_minutes=parse_duration(row.get("Duration")),
            publication_status=published, published_at=row.get("Published") or None,
            exclusion_reasons=reasons, is_discoverable=not reasons, snapshot_id=manifest["snapshot_id"],
            extracted_at=manifest["extracted_at"],
            raw={"url": row["Url"], "IsDeleted": row["IsDeleted"], "StatusId": row.get("StatusId"),
                 "access_rule": "public_auxiliary_page_policy_v1", "access_rule_is_inferred": True}))

    aliases = build_aliases(materials)
    resolver = {(a.source_table, a.source_record_id): a.material_key for a in aliases}
    owners = {m.material_key: m for m in materials}
    if len(owners) != len(materials):
        raise ValueError("Duplicate canonical material")
    blocks, dropped = [], Counter()
    def add(material_key, source_table, source_id, order, value, protected=False, kind="body", entitlement=None):
        if not value:
            return
        blocks.append(ContentBlock(block_id=f"{source_table}:{source_id}", material_key=material_key,
            source_table=source_table, source_record_id=source_id, order=order, text=value,
            access_scope="entitled" if protected else "public", entitlement_key=(entitlement or material_key) if protected else None,
            content_kind=kind))

    for material in materials:
        identity = material.source_identities[0]
        metadata = "\n\n".join(dict.fromkeys([material.title] + material.descriptions + material.topics + material.tags))
        add(material.material_key, identity.table + ".card", identity.record_id, -1, metadata, kind="metadata")

    # Explicit promotional blocks are identified by their actual Params keys.
    for block_table, parent_column, parent_table in BODY_SOURCES:
        for row in table(input_dir, block_table):
            key = resolver.get((parent_table, row[parent_column]))
            if not key:
                raise ValueError(f"Orphan source block: {block_table}")
            value = block_text(row["HtmlContent"], row["Params"])
            if value:
                add(key, block_table, row["Id"], integer(row["Order"]), value,
                    protected=owners[key].access_type != "Открытый")
            else:
                dropped[block_table] += 1

    # Use legacy body fields only when there is no extracted embedded body.
    body_keys = {b.material_key for b in blocks if b.content_kind == "body"}
    for row in table(input_dir, "Articles"):
        key = resolver[("Articles", row["Id"])]
        if key not in body_keys:
            add(key, "Articles.Content", row["Id"], 0, extract_text(row["Content"]),
                protected=owners[key].access_type != "Открытый")

    lessons = {x["Id"]: x for x in table(input_dir, "Lessons")}
    lesson_blocks = defaultdict(list)
    for row in table(input_dir, "LessonEmbedItems"):
        if row["LessonId"] not in lessons:
            raise ValueError("Orphan LessonEmbedItems")
        lesson_blocks[row["LessonId"]].append(row)
    child_links = []
    for row in table(input_dir, "CourseLessonBindings"):
        key = resolver.get(("Courses", row["CourseId"]))
        lesson = lessons.get(row["LessonId"])
        if not key or lesson is None:
            raise ValueError("Orphan course/lesson relation")
        child_links.append(ChildLink(source_record_id=row["Id"], material_key=key, lesson_id=row["LessonId"],
            order=integer(row["Order"]), is_closed=parse_bool(row["IsClosed"]), is_trial=parse_bool(row["IsTrial"]),
            closed_until=row["ClosedUntil"] or None))
        if parse_bool(lesson["IsDeleted"]) is True or parse_bool(lesson["IsGroup"]) is True:
            continue
        # Never expose lesson bodies in public discovery, including trial lessons.
        # Exact course entitlement is required; a trial access flow can be added later.
        children = sorted(lesson_blocks[row["LessonId"]], key=lambda x: (integer(x["Order"]), x["Id"]))
        has_body = False
        for child in children:
            value = block_text(child["HtmlContent"], child["Params"])
            if value:
                has_body = True
                add(key, "LessonEmbedItems", child["Id"], 100000 + integer(row["Order"]) * 10000 + integer(child["Order"]),
                    value, protected=True, entitlement=key + "/lesson:" + lesson["Id"])
        if not has_body:
            add(key, "Lessons.Content", lesson["Id"], 100000 + integer(row["Order"]) * 10000,
                extract_text(lesson["Content"]), protected=True, entitlement=key + "/lesson:" + lesson["Id"])
    # Optional supplied files: filename is the verified source FileId + extension.
    file_lookup = {x["Id"]: x for x in table(input_dir, "Files")}
    for row in table(input_dir, "Documents"):
        material = owners[resolver[("Documents", row["Id"])]]
        file = file_lookup.get(row["FileId"])
        if file is None or parse_bool(file["IsDeleted"]) is True:
            material.quality_flags.append("file_missing_or_deleted")
            continue
        path = (document_dir / (file["Id"] + "." + file["Extension"].lstrip("."))) if document_dir else None
        if path is None or not path.is_file():
            material.quality_flags.append("file_not_supplied_locally")
            continue
        if path.resolve().parent != document_dir.resolve():
            raise ValueError("File path outside supplied document directory")
        value, state = extract_local_file(path)
        if value:
            add(material.material_key, "Files", file["Id"], 99999, extract_text(value),
                protected=material.access_type != "Открытый")
        else:
            material.quality_flags.append(state)

    # Remove exact repeated promotional paragraphs; retain source blocks as evidence
    # for all other text. Ordinary repeated domain definitions are not discarded.
    import re
    paragraphs = defaultdict(set)
    for b in blocks:
        if b.content_kind == "body":
            for paragraph in b.text.split("\n\n"):
                paragraphs[paragraph].add(b.material_key)
    boilerplate = {p for p, keys in paragraphs.items() if len(keys) >= 10 and re.search(
        r"откр[оы].*сч[её]т|подписывайтесь|подпи[шс].*канал|оставьте.*заявк", p, re.I)}
    cleaned = []
    for b in blocks:
        if b.content_kind == "body":
            b.text = "\n\n".join(p for p in b.text.split("\n\n") if p not in boilerplate)
        if b.text:
            cleaned.append(b)
    blocks = cleaned
    signatures = [(b.material_key, b.block_id) for b in blocks]
    if len(set(signatures)) != len(signatures):
        raise ValueError("Duplicate block identity within material")
    by_material = defaultdict(list)
    for b in blocks:
        by_material[b.material_key].append(b)
    for material in materials:
        body = [b for b in by_material[material.material_key] if b.content_kind == "body"]
        material.content_coverage = ("partial_body" if material.item_type == "document" and body and
            any(flag in material.quality_flags for flag in ("file_not_supplied_locally", "file_missing_or_deleted", "image_only_or_unreadable", "unreadable", "unsupported_or_invalid_format")) else "body" if body else "metadata_only")
        if not body:
            material.quality_flags.append("metadata_only")
        material.content_hash = digest({"title": material.title, "descriptions": material.descriptions,
            "topics": material.topics, "tags": material.tags, "industry": material.industry_labels,
            "access": material.access_type,
            "blocks": [b.model_dump() for b in sorted(by_material[material.material_key], key=lambda b: (b.order,b.block_id))]})
    return sorted(materials, key=lambda x:x.material_key), aliases, sorted(blocks,key=lambda b:(b.material_key,b.order,b.block_id)), child_links, manifest, {
        "nontext_blocks": dict(dropped), "removed_repeated_promotional_paragraphs": len(boilerplate)}
