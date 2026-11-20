"""Build a SYNTHETIC demo catalogue and its BM25 retrieval index.

The private organizer catalogue is not part of this repository. This script
reads the tracked, clearly-labelled synthetic course catalogue in
``data/courses/courses.csv`` (12 products with prices, durations and skills),
adds six sample materials of other formats, and runs the *real* preparation
pipeline over them. ``scripts/seed_courses.py`` loads the same CSV into the
product ``courses`` table, so the database and the ML serving path agree.

Nothing here is organizer data. Every card produced from this catalogue is
labelled "synthetic" in the UI, and every price and duration is illustrative.

Usage:
    python scripts/build_demo_catalog.py \
        --catalog-dir data/processed/catalog \
        --index-dir artifacts/retrieval
"""
import argparse
import csv
import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.data_preparation.chunking import chunk_blocks, digest
from app.data_preparation.audit import audit_catalog
from app.data_preparation.contracts import CATALOG_VERSION, CLEANING_VERSION, ENCODER, ENCODER_REVISION
from app.data_preparation.eligibility import public_chunks
from app.data_preparation.history_io import publish_bundle, write_jsonl
from app.data_preparation.pipeline import build_catalog
from app.data_preparation.retrieval_bundle import build_index, catalog_search_inputs
from app.data_preparation.source import EXPORT_COLUMNS
from app.ml.lsa_retriever import LsaRetriever
from app.ml.retrieval_contracts import RetrievalPolicy

DEMO_TITLE = "Synthetic demo catalogue (not organizer data)"

ARTICLES = [
    {
        "id": "a-clients",
        "title": "Как найти первых клиентов",
        "description": "Практический разбор первых продаж: где искать клиентов и что говорить.",
        "body": [
            "Первые клиенты почти всегда приходят из окружения: знакомые, бывшие коллеги, локальные сообщества. Начните с десяти разговоров и запишите, какая боль повторяется чаще всего.",
            "Второй канал — партнёрства с теми, у кого уже есть ваша аудитория. Обмен рекомендациями дешевле рекламы и быстрее проверяет спрос.",
            "Считайте не показы, а количество диалогов и заявок. Если из десяти разговоров нет ни одной заявки, меняйте не канал, а предложение.",
        ],
    },
    {
        "id": "a-cash",
        "title": "Кассовый разрыв: как заметить заранее",
        "description": "Что такое кассовый разрыв и как его избежать без кредита.",
        "topic": "t-finance",
        "body": [
            "Кассовый разрыв — это когда деньги уже потрачены, а выручка ещё не пришла. Он виден за две-три недели, если вести простой платёжный календарь по неделям.",
            "Разделите расходы на обязательные и гибкие. Гибкие можно сдвинуть на две недели, и часто этого достаточно, чтобы пройти низкий сезон.",
            "Договоритесь с поставщиками об отсрочке заранее, а не в день платежа. Отсрочка на 14 дней обычно дешевле любого кредита.",
        ],
    },
    {
        "id": "a-taxes",
        "title": "Налоги для ИП и небольшого бизнеса",
        "description": "НДС, НДФЛ и выбор налогового режима без штрафов.",
        "topic": "t-taxes",
        "body": [
            "Начните с режима: самозанятость, ИП или ООО. Режим определяет, какие налоги вы платите и какую отчётность сдаёте.",
            "НДС появляется при превышении лимита или при работе с крупными компаниями. Заранее посчитайте, как он повлияет на цену и маржу.",
            "НДФЛ и страховые взносы с зарплаты сотрудников — часть стоимости найма. Учитывайте их в бюджете до того, как обещаете оклад.",
        ],
    },
    {
        "id": "a-retail",
        "title": "Продажи в розничном магазине: что делать при падении",
        "description": "Как найти причину падения продаж в магазине одежды и вернуть поток покупателей.",
        "topic": "t-sales",
        "body": [
            "Сначала разделите падение на трафик и конверсию: сколько людей заходит в магазин или на карточку товара и сколько из них покупает.",
            "Если трафик упал, проверьте каналы: карты, соцсети, локальные рекомендации и повторные визиты. Если конверсия — ассортимент, цену и витрину.",
            "Считайте продажи по неделям и сравнивайте с прошлым годом. Один плохой месяц — ещё не тренд, но три подряд требуют нового предложения.",
        ],
    },
    {
        "id": "a-start",
        "title": "Старт бизнеса: форма, регистрация и первые документы",
        "description": "Как выбрать ИП или ООО, пройти регистрацию и не забыть обязательные документы.",
        "topic": "t-process",
        "body": [
            "Начните с формы: самозанятость, ИП или ООО. Сравните ответственность, налоги и отчётность. Если вы работаете один и без сотрудников, ИП обычно проще и дешевле.",
            "Для регистрации проверьте название компании на уникальность, подготовьте заявление, коды ОКВЭД и учредительные документы. Для ООО добавьте устав и решение об учреждении.",
            "После регистрации откройте расчётный счёт, оформите онлайн-кассу при приёме оплаты и подпишите договоры с контрагентами. Доверенности выдавайте представителю только на конкретные действия и храните вместе с учредительными документами компании.",
        ],
    },
    {
        "id": "a-accounting",
        "title": "Бухгалтерия и кадры: что закрыть в первый месяц",
        "description": "Документы, отчётность, зарплата и кадровый учёт для небольшого бизнеса.",
        "topic": "t-taxes",
        "body": [
            "Ведите доходы и расходы каждую неделю: сохраняйте первичные документы, счета-фактуры, акты и акты сверки расчётов. Это основа налоговой отчётности и управленческих решений.",
            "В кадрах проверьте трудовой договор, приказ о приёме, график смен и отпусков, расчёт зарплаты и страховых взносов. Кадровые ошибки стоят дороже, чем кажется.",
            "Онлайн-касса и фискальные документы нужны при приёме оплаты от покупателей, счета-фактуры — при работе с НДС. Сроки сдачи отчётности и уплаты налогов проверяйте заранее.",
        ],
    },
]

COURSES_CSV = ROOT / "data/courses/courses.csv"

CATEGORY_RU = {
    "marketing": "Маркетинг: клиенты, позиционирование бренда и эффективность каналов.",
    "sales": "Продажи: переговоры, работа с возражениями и повторяемая воронка.",
    "finance": "Финансы: выручка, прибыль, юнит-экономика и кассовый разрыв.",
    "management": "Управление: найм, процессы, приоритизация и операционная устойчивость.",
    "programming": "Программирование и данные: Python, SQL, автоматизация и аналитика.",
    "entrepreneurship": "Предпринимательство: фандрайзинг, питч инвесторам и запуск бизнеса.",
}

TOPIC_BY_CATEGORY = {
    "marketing": "t-marketing",
    "sales": "t-sales",
    "finance": "t-finance",
    "management": "t-management",
    "programming": "t-programming",
    "entrepreneurship": "t-entrepreneurship",
}


def load_courses(path: Path = COURSES_CSV) -> list[dict]:
    """Read the tracked synthetic catalogue with prices, durations and skills."""
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise SystemExit(f"empty course catalogue: {path}")
    courses = []
    for row in rows:
        courses.append({
            "id": row["course_id"].strip(),
            "title": row["title_ru"].strip() or row["title"].strip(),
            "title_en": row["title"].strip(),
            "description": (row.get("description_ru") or row["description"]).strip(),
            "skills": [x.strip() for x in row["skills"].split(";") if x.strip()],
            "objectives": [x.strip() for x in row["objectives"].split(";") if x.strip()],
            "category": row["category"].strip(),
            "difficulty": row["difficulty"].strip(),
            "duration_minutes": int(float(row["duration_minutes"])),
            "price": float(row["price"]),
            "has_free_material": row["has_free_material"].strip().lower() == "true",
        })
    return courses

DOCUMENTS = [
    {
        "id": "d-processes",
        "title": "Чек-лист: процессы в малом бизнесе",
        "description": "Пять процессов, которые стоит описать первыми.",
        "body": [
            "Опишите пять процессов: заявка, счёт, отгрузка, возврат и отчёт. На каждый хватит одной страницы и списка шагов.",
            "Назначьте владельца процесса и срок. Процесс без владельца не работает, даже если он записан.",
        ],
    },
]

WEBINARS = [
    {
        "id": "w-sales",
        "title": "Продажи без бюджета",
        "description": "Вебинар о том, как получать заявки без платной рекламы.",
        "body": [
            "Разбираем бесплатные каналы: сообщества, партнёрства, повторные продажи и рекомендации. Показываем, как считать стоимость заявки в каждом канале. Для повторных продаж достаточно простой CRM или таблицы: откуда пришёл клиент, что купил и когда вернуться.",
        ],
    },
]


ENTITY_TYPE = {
    "articles": "8ede4179-0faf-407d-a4fc-1d94f9a63089",
    "courses": "8b440b1a-00c3-423a-9bae-3376475eb203",
    "documents": "da1ad865-8605-4ab1-9f6c-4489a26fbc35",
    "webinars": "ece4acf3-5dd3-47b9-9f08-99c0d6203cc7",
}


def build_source(directory: Path) -> None:
    """Write the export CSVs the preparation pipeline expects."""
    rows = {name: [] for name in EXPORT_COLUMNS}
    rows["Statuses"] = [{"Id": "published", "Title": "Опубликовано"}]
    rows["CourseTypes"] = [
        {"Id": "open", "Title": "Открытый", "IsDeleted": "f"},
        {"Id": "subscription", "Title": "По подписке", "IsDeleted": "f"},
    ]
    rows["Topics"] = [
        {"Id": "t-clients", "Title": "Клиенты и продажи", "IsDeleted": "f", "IsPublic": "t"},
        {"Id": "t-taxes", "Title": "Налоги", "IsDeleted": "f", "IsPublic": "t"},
        {"Id": "t-finance", "Title": "Финансы", "IsDeleted": "f", "IsPublic": "t"},
        {"Id": "t-hiring", "Title": "Сотрудники", "IsDeleted": "f", "IsPublic": "t"},
        {"Id": "t-process", "Title": "Процессы", "IsDeleted": "f", "IsPublic": "t"},
        {"Id": "t-marketing", "Title": "Маркетинг", "IsDeleted": "f", "IsPublic": "t"},
        {"Id": "t-sales", "Title": "Продажи", "IsDeleted": "f", "IsPublic": "t"},
        {"Id": "t-management", "Title": "Управление", "IsDeleted": "f", "IsPublic": "t"},
        {"Id": "t-programming", "Title": "Программирование", "IsDeleted": "f", "IsPublic": "t"},
        {"Id": "t-entrepreneurship", "Title": "Предпринимательство", "IsDeleted": "f", "IsPublic": "t"},
    ]
    rows["Tags"] = [{"Id": "tag-demo", "Title": "Демо", "IsDeleted": "f"}]
    rows["Industries"] = [{"Id": "ind-small", "Title": "Малый бизнес", "IsDeleted": "f"}]

    settings = []

    def add_settings(item_id: str, entity: str, type_id: str, topic: str) -> None:
        settings.append({"Id": "set-" + item_id, "EntityId": item_id, "EntityTypeId": entity,
                         "StatusId": "published", "TypeId": type_id, "IsDeleted": "f",
                         "Published": "2026-01-01"})
        rows["ContentSettingsTopics"].append({"ContentSettingsId": "set-" + item_id, "TopicId": topic, "Order": "1"})
        rows["ContentSettingsTags"].append({"ContentSettingsId": "set-" + item_id, "TagId": "tag-demo", "Order": "1"})
        rows["ContentSettingsIndustries"].append({"ContentSettingsId": "set-" + item_id, "IndustryId": "ind-small", "Order": "1"})

    for article in ARTICLES:
        topic = article.get("topic", "t-clients")
        rows["Articles"].append({
            "Id": article["id"], "Title": article["title"], "Description": article["description"],
            "CardDescription": article["description"], "Duration": "7 мин", "StatusId": "published",
            "TypeId": "open", "IsPublic": "t", "IsClosed": "f", "IsDeleted": "f",
            "Published": "2026-01-01", "Url": "demo-" + article["id"],
        })
        for order, paragraph in enumerate(article["body"], start=1):
            rows["ArticleEmbedItems"].append({
                "Id": f"{article['id']}-b{order}", "ArticleId": article["id"], "Order": str(order),
                "Type": "0", "HtmlContent": f"<p>{paragraph}</p>", "Params": "{}",
            })
        add_settings(article["id"], ENTITY_TYPE["articles"], "open", topic)

    for course in load_courses():
        type_id = "open" if course["price"] == 0 else "subscription"
        rows["Courses"].append({
            "Id": course["id"], "Title": course["title"],
            "Description": f"{course['description']} {CATEGORY_RU[course['category']]}",
            "DescriptionAdditional": (f"{course['title_en']}. Навыки: {', '.join(course['skills'])}. "
                                      f"Результаты: {'; '.join(course['objectives'])}."),
            "Target": "", "Duration": f"{course['duration_minutes']} мин",
            "LessonQuantity": str(len(course["objectives"])),
            "Cost": f"{course['price']:g}" if course["price"] else "",
            "TypeId": type_id, "StatusId": "published",
            "HasTrial": "t" if course["has_free_material"] else "f",
            "IsClosed": "f", "IsDeleted": "f", "Published": "2026-01-01",
            "Url": "demo-" + course["id"],
        })
        for number, objective in enumerate(course["objectives"], start=1):
            lesson_id = f"{course['id']}-l{number}"
            rows["Lessons"].append({"Id": lesson_id, "Title": f"Урок {number}. {objective}",
                                    "Description": "", "Content": "",
                                    "Duration": "15 мин", "IsDeleted": "f", "IsGroup": "f", "TypeId": "0"})
            rows["CourseLessonBindings"].append({"Id": f"{course['id']}-bind{number}", "CourseId": course["id"],
                                                 "LessonId": lesson_id, "Order": str(number),
                                                 "IsTrial": "t" if number == 1 else "f",
                                                 "IsClosed": "f", "ClosedUntil": ""})
            text = (f"{objective}. {CATEGORY_RU[course['category']]} "
                    f"Навыки: {', '.join(course['skills'])}.")
            rows["LessonEmbedItems"].append({"Id": lesson_id + "-b1", "LessonId": lesson_id, "Order": "1",
                                             "Type": "0", "HtmlContent": f"<p>{text}</p>", "Params": "{}"})
        add_settings(course["id"], ENTITY_TYPE["courses"], type_id, TOPIC_BY_CATEGORY[course["category"]])

    for document in DOCUMENTS:
        rows["Documents"].append({"Id": document["id"], "Title": document["title"], "Description": document["description"],
                                  "TypeId": "open", "StatusId": "published", "IsDeleted": "f",
                                  "Published": "2026-01-01", "Url": "demo-" + document["id"],
                                  "Extension": "pdf", "Size": "42", "FileId": ""})
        for order, paragraph in enumerate(document["body"], start=1):
            rows["DocumentEmbedItems"].append({"Id": f"{document['id']}-b{order}", "DocumentId": document["id"],
                                               "Order": str(order), "Type": "0",
                                               "HtmlContent": f"<p>{paragraph}</p>", "Params": "{}"})
        add_settings(document["id"], ENTITY_TYPE["documents"], "open", "t-process")

    for webinar in WEBINARS:
        rows["Webinars"].append({"Id": webinar["id"], "Title": webinar["title"], "Description": webinar["description"],
                                 "DescriptionExt": " ".join(webinar["body"]), "Duration": "45 мин",
                                 "StatusId": "published", "TypeId": "open", "IsClosed": "f", "IsDeleted": "f",
                                 "Url": "demo-" + webinar["id"], "StartsAt": "", "EndsAt": ""})
        add_settings(webinar["id"], ENTITY_TYPE["webinars"], "open", "t-clients")

    rows["ContentSettings"] = settings
    directory.mkdir(parents=True, exist_ok=True)
    for name, columns in EXPORT_COLUMNS.items():
        with (directory / (name + ".csv")).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows[name])

    files = {}
    for name, columns in EXPORT_COLUMNS.items():
        path = directory / (name + ".csv")
        with path.open(encoding="utf-8", newline="") as stream:
            count = sum(1 for _ in csv.DictReader(stream))
        files[name] = {"filename": path.name, "rows": count,
                       "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "columns": list(columns)}
    manifest = {"snapshot_id": hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(),
                "files": files, "extracted_at": "2026-01-01T00:00:00+00:00", "source": "synthetic_demo"}
    (directory / "source_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")


class CharacterTokenizer:
    """Same budget model as the test fixtures: no private tokenizer needed."""

    def count(self, text: str) -> int:
        return len(text) + 2


def build(catalog_dir: Path, index_dir: Path, embedding_dir: Path | None = None) -> dict:
    with tempfile.TemporaryDirectory(prefix="alfa-demo-source-") as temp:
        source = Path(temp)
        build_source(source)
        materials, aliases, blocks, links, manifest, _ = build_catalog(source)

    tokenizer = CharacterTokenizer()
    chunks = chunk_blocks(materials, blocks, tokenizer, target_tokens=150)
    public = public_chunks(materials, chunks)
    with tempfile.TemporaryDirectory(prefix="alfa-demo-source-") as temp:
        build_source(Path(temp))
        report = audit_catalog(materials, aliases, blocks, chunks, public, links, manifest)
    if not report.get("passed", False):
        raise SystemExit("synthetic catalogue audit failed: " + json.dumps(report, ensure_ascii=False)[:800])

    config = {"catalog_version": CATALOG_VERSION, "cleaning_version": CLEANING_VERSION,
              "encoder": ENCODER, "encoder_revision": ENCODER_REVISION,
              "target_tokens": 150, "max_tokens": 200, "overlap_tokens": 0,
              "route_version": "kurs-routes-v1", "auxiliary_access_policy": "public_auxiliary_page_policy_v1",
              "demo": True, "dataset": DEMO_TITLE}
    bundle_id = digest({"snapshot": manifest["snapshot_id"], "config": config,
                        "materials": [m.model_dump() for m in materials],
                        "chunks": [c.chunk_id for c in chunks]})
    outputs = {"materials.jsonl": materials, "aliases.jsonl": aliases,
               "content_blocks.jsonl": blocks, "chunks.jsonl": chunks,
               "public_chunks.jsonl": public, "child_links.jsonl": links,
               "audit.json": report}
    catalog_bundle = publish_bundle(catalog_dir, bundle_id, outputs, {
        "source_snapshot": manifest["snapshot_id"], "extracted_at": manifest["extracted_at"],
        "config": config, "demo": True, "dataset": DEMO_TITLE,
    })
    # Demo policy: keep the full BM25 ranking even for short Russian queries, so
    # the feed can always fill a six-card slate from the 16-product catalogue.
    index_path, audit = build_index(catalog_dir, index_dir, ROOT, RetrievalPolicy(min_similarity=0.0001))
    dense_output = None
    if embedding_dir is not None:
        search_materials, chunks, _ = catalog_search_inputs(catalog_dir)
        dense = LsaRetriever(min_similarity=0.10).fit(search_materials, chunks)
        dense_path = dense.save(embedding_dir, metadata={
            "catalog_bundle_id": catalog_bundle.name,
            "retrieval_bundle_id": index_path.name,
            "dataset": DEMO_TITLE,
        })
        dense_output = {
            "path": str(dense_path), "rows": len(dense.rows),
            "dimensions": int(dense.vectors.shape[1]),
            "materials": len({row.material_key for row in dense.rows}),
        }
    return {"catalog": str(catalog_bundle), "index": str(index_path), "audit": audit,
            "embedding": dense_output,
            "materials": len(materials), "public_chunks": len(public)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog-dir", type=Path, default=ROOT / "data/processed/catalog")
    parser.add_argument("--index-dir", type=Path, default=ROOT / "artifacts/retrieval")
    parser.add_argument("--embedding-dir", type=Path, default=None,
                        help="write the dense vector dataset here (optional)")
    args = parser.parse_args()
    print(json.dumps(build(args.catalog_dir, args.index_dir, args.embedding_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
