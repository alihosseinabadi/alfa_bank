"""Generate the public synthetic retrieval benchmark used by the light-path evaluation.

Why this exists: the real Alfa-Kurs catalog, judgments and artifacts are private,
so the retrieval numbers in ``docs/quality_stage56.md`` cannot be reproduced in
this repository. This script builds a fully public, deterministic stand-in so the
retrieval comparison can at least be *run* by anyone, and so regressions are
visible.

Honesty note (also written into the manifest):

* Relevance is **construction-derived**, not human-judged. Each query targets one
  material on purpose (grade 2); other materials of the same topic get grade 1;
  everything else gets grade 0.
* Because the query set is constructed, the "inflected" family deliberately uses
  word forms that differ from the indexed text. That family is *expected* to
  favour morphologically aware retrieval. It is reported separately from the
  "natural" family for exactly that reason.
* This benchmark therefore measures behaviour and regression, not real-world
  relevance. Never quote these numbers as production NDCG.

Usage:
    python scripts/make_light_benchmark.py            # write, if absent
    python scripts/make_light_benchmark.py --force    # rewrite
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "data" / "synthetic" / "light_benchmark_v1"

BENCHMARK_VERSION = "light-benchmark-v1"
# Frozen before any measurement. Changing it invalidates every reported number.
HOLDOUT_SALT = "alfa-kurs-light-benchmark-2026-holdout"
HOLDOUT_MODULUS = 10
HOLDOUT_RESIDUES = (0, 1, 2)

# ---------------------------------------------------------------------------
# Catalog content. One entry per topic; each concept carries the indexed text
# and two hand-written query phrasings (a natural one and a paraphrased one).
# ---------------------------------------------------------------------------

TOPICS: list[dict[str, Any]] = [
    {
        "id": "unit_economics",
        "name": "Юнит-экономика",
        "tags": ["юнит-экономика", "ltv", "cac", "маржа"],
        "concepts": [
            {
                "id": "ue1",
                "title": "Юнит-экономика продукта",
                "body": (
                    "Юнит-экономика показывает, сколько прибыли приносит один клиент "
                    "после вычета стоимости привлечения."
                ),
                "natural": "как посчитать юнит-экономику продукта",
                "paraphrase": "как считать экономику клиента и прибыль с клиента",
            },
            {
                "id": "ue2",
                "title": "LTV и CAC",
                "body": "Метрики LTV и CAC помогают понять, окупается ли привлечение покупателя.",
                "natural": "что такое ltv и cac",
                "paraphrase": "как соотносятся стоимость привлечения клиента и прибыль с клиента",
            },
            {
                "id": "ue3",
                "title": "Маржинальность заказа",
                "body": "Маржинальность заказа равна выручке минус переменные расходы на его выполнение.",
                "natural": "как рассчитать маржинальность заказа",
                "paraphrase": "как посчитать рентабельность одного заказа",
            },
        ],
    },
    {
        "id": "clients",
        "name": "Клиентский сервис",
        "tags": ["клиентский сервис", "удержание", "лояльность", "покупатели"],
        "concepts": [
            {
                "id": "cl1",
                "title": "Клиентский сервис",
                "body": "Клиентский сервис влияет на то, вернётся ли покупатель за повторной покупкой.",
                "natural": "как улучшить клиентский сервис",
                "paraphrase": "как наладить обслуживание клиентов",
            },
            {
                "id": "cl2",
                "title": "Удержание покупателей",
                "body": "Удержание покупателей дешевле, чем привлечение новых клиентов.",
                "natural": "как повысить удержание покупателей",
                "paraphrase": "как удерживать клиентов дольше",
            },
            {
                "id": "cl3",
                "title": "Работа с жалобами",
                "body": "Жалоба клиента — это возможность вернуть лояльность и исправить процесс.",
                "natural": "как работать с жалобами клиентов",
                "paraphrase": "что делать с претензиями покупателя",
            },
        ],
    },
    {
        "id": "marketing",
        "name": "Маркетинг",
        "tags": ["маркетинг", "реклама", "трафик", "продвижение"],
        "concepts": [
            {
                "id": "mk1",
                "title": "Каналы привлечения",
                "body": "Каналы привлечения различаются стоимостью клика и качеством аудитории.",
                "natural": "какие каналы привлечения выбрать",
                "paraphrase": "где искать клиентов для бизнеса",
            },
            {
                "id": "mk2",
                "title": "Рекламный бюджет",
                "body": "Рекламный бюджет стоит планировать от целевой стоимости привлечения.",
                "natural": "как распределить рекламный бюджет",
                "paraphrase": "сколько тратить на рекламу",
            },
            {
                "id": "mk3",
                "title": "Контент-маркетинг",
                "body": "Контент-маркетинг приводит клиентов через полезные статьи и видео.",
                "natural": "как построить контент-маркетинг",
                "paraphrase": "как продвигать бизнес через статьи",
            },
        ],
    },
    {
        "id": "sales",
        "name": "Продажи",
        "tags": ["продажи", "сделки", "возражения", "конверсия"],
        "concepts": [
            {
                "id": "sl1",
                "title": "Техника продаж",
                "body": "Техника продаж строится на выявлении потребности и работе с возражениями.",
                "natural": "как освоить технику продаж",
                "paraphrase": "как продавать товар клиенту",
            },
            {
                "id": "sl2",
                "title": "Скрипты звонков",
                "body": "Скрипты звонков задают структуру разговора и снижают потерю заявок.",
                "natural": "как составить скрипты звонков",
                "paraphrase": "что говорить клиенту по телефону",
            },
            {
                "id": "sl3",
                "title": "Воронка продаж",
                "body": "Воронка продаж показывает, на каком этапе теряются заявки.",
                "natural": "как построить воронку продаж",
                "paraphrase": "как считать конверсию заявок в сделки",
            },
        ],
    },
    {
        "id": "finance",
        "name": "Финансы",
        "tags": ["финансы", "деньги", "учёт", "платежи"],
        "concepts": [
            {
                "id": "fn1",
                "title": "Денежный поток",
                "body": "Денежный поток показывает движение денег, а не бухгалтерскую прибыль.",
                "natural": "как управлять денежным потоком",
                "paraphrase": "как считать движение денег в компании",
            },
            {
                "id": "fn2",
                "title": "Кассовый разрыв",
                "body": "Кассовый разрыв возникает, когда расходы опережают поступления.",
                "natural": "как закрыть кассовый разрыв",
                "paraphrase": "что делать если не хватает денег на платежи",
            },
            {
                "id": "fn3",
                "title": "Финансовый учёт",
                "body": "Финансовый учёт даёт владельцу цифры для решений, а не отчётность для налоговой.",
                "natural": "как наладить финансовый учёт",
                "paraphrase": "как вести учёт доходов и расходов",
            },
        ],
    },
    {
        "id": "legal",
        "name": "Право и регистрация",
        "tags": ["регистрация", "документы", "договор", "ип"],
        "concepts": [
            {
                "id": "lg1",
                "title": "Регистрация ИП",
                "body": "Регистрация ИП занимает несколько дней и требует заявления и госпошлины.",
                "natural": "как пройти регистрацию ип",
                "paraphrase": "как оформить индивидуального предпринимателя",
            },
            {
                "id": "lg2",
                "title": "Налоговый режим",
                "body": "Налоговый режим выбирают по выручке, числу сотрудников и видам деятельности.",
                "natural": "как выбрать налоговый режим",
                "paraphrase": "какую систему налогообложения подобрать",
            },
            {
                "id": "lg3",
                "title": "Договор с поставщиком",
                "body": "Договор с поставщиком должен фиксировать сроки, штрафы и порядок приёмки.",
                "natural": "как составить договор с поставщиком",
                "paraphrase": "что проверить в контракте с поставщиком",
            },
        ],
    },
    {
        "id": "hiring",
        "name": "Найм",
        "tags": ["найм", "команда", "сотрудники", "собеседование"],
        "concepts": [
            {
                "id": "hr1",
                "title": "Найм сотрудников",
                "body": "Найм сотрудников начинается с описания задач и профиля кандидата.",
                "natural": "как организовать найм сотрудников",
                "paraphrase": "как нанимать людей в команду",
            },
            {
                "id": "hr2",
                "title": "Собеседование",
                "body": "Собеседование проверяет не только навыки, но и мотивацию кандидата.",
                "natural": "как провести собеседование",
                "paraphrase": "как оценить кандидата на встрече",
            },
            {
                "id": "hr3",
                "title": "Адаптация новичка",
                "body": "Адаптация новичка сокращает время до первой самостоятельной задачи.",
                "natural": "как выстроить адаптацию новичка",
                "paraphrase": "как вводить сотрудника в работу",
            },
        ],
    },
    {
        "id": "tax",
        "name": "Налоги",
        "tags": ["налоги", "ндс", "взносы", "усн"],
        "concepts": [
            {
                "id": "tx1",
                "title": "НДС",
                "body": "НДС уплачивается с добавленной стоимости и требует раздельного учёта.",
                "natural": "как считать ндс",
                "paraphrase": "как начислять налог на добавленную стоимость",
            },
            {
                "id": "tx2",
                "title": "Упрощённая система",
                "body": "Упрощённая система налогообложения заменяет ндс и налог на прибыль одним платежом.",
                "natural": "как перейти на упрощённую систему",
                "paraphrase": "как работать по усн",
            },
            {
                "id": "tx3",
                "title": "Страховые взносы",
                "body": "Страховые взносы платятся с фонда оплаты труда каждого сотрудника.",
                "natural": "как считать страховые взносы",
                "paraphrase": "сколько платить взносов за сотрудников",
            },
        ],
    },
    {
        "id": "marketplace",
        "name": "Маркетплейсы",
        "tags": ["маркетплейс", "карточка товара", "доставка", "продавец"],
        "concepts": [
            {
                "id": "mp1",
                "title": "Карточка товара",
                "body": "Карточка товара продаёт через фото, заголовок и характеристики.",
                "natural": "как оформить карточку товара",
                "paraphrase": "как заполнить страницу товара на маркетплейсе",
            },
            {
                "id": "mp2",
                "title": "Логистика заказов",
                "body": "Логистика заказов определяет срок доставки и стоимость хранения.",
                "natural": "как наладить логистику заказов",
                "paraphrase": "как доставлять товары покупателям",
            },
            {
                "id": "mp3",
                "title": "Рейтинг продавца",
                "body": "Рейтинг продавца зависит от отзывов, сроков и доли возвратов.",
                "natural": "как повысить рейтинг продавца",
                "paraphrase": "как улучшить оценки магазина",
            },
        ],
    },
    {
        "id": "operations",
        "name": "Операции",
        "tags": ["процессы", "автоматизация", "качество", "закупки"],
        "concepts": [
            {
                "id": "op1",
                "title": "Бизнес-процессы",
                "body": "Бизнес-процессы описывают, кто и как выполняет повторяющиеся задачи.",
                "natural": "как описать бизнес-процессы",
                "paraphrase": "как навести порядок в повторяющихся задачах",
            },
            {
                "id": "op2",
                "title": "Автоматизация рутины",
                "body": "Автоматизация рутины освобождает время на продажи и развитие.",
                "natural": "что можно автоматизировать в рутине",
                "paraphrase": "как убрать ручную работу из процессов",
            },
            {
                "id": "op3",
                "title": "Контроль качества",
                "body": "Контроль качества фиксирует стандарт и точку, где он нарушается.",
                "natural": "как наладить контроль качества",
                "paraphrase": "как проверять качество работы",
            },
        ],
    },
    {
        "id": "product",
        "name": "Продукт",
        "tags": ["продукт", "спрос", "цена", "гипотезы"],
        "concepts": [
            {
                "id": "pr1",
                "title": "Исследование спроса",
                "body": "Исследование спроса проверяет, готовы ли клиенты платить за продукт.",
                "natural": "как провести исследование спроса",
                "paraphrase": "как понять нужен ли продукт покупателям",
            },
            {
                "id": "pr2",
                "title": "Ценовая стратегия",
                "body": "Ценовая стратегия связывает цену с ценностью и позицией на рынке.",
                "natural": "как выбрать ценовую стратегию",
                "paraphrase": "как назначить цену на продукт",
            },
            {
                "id": "pr3",
                "title": "Тестирование гипотез",
                "body": "Тестирование гипотез начинается с самой рискованной части идеи.",
                "natural": "как тестировать гипотезы продукта",
                "paraphrase": "как проверять идеи до запуска",
            },
        ],
    },
    {
        "id": "funding",
        "name": "Финансирование",
        "tags": ["инвестор", "кредит", "грант", "бизнес-план"],
        "concepts": [
            {
                "id": "fd1",
                "title": "Бизнес-план для инвестора",
                "body": "Бизнес-план для инвестора показывает модель, цифры и возврат вложений.",
                "natural": "как составить бизнес-план для инвестора",
                "paraphrase": "что показать инвестору в презентации проекта",
            },
            {
                "id": "fd2",
                "title": "Кредит для бизнеса",
                "body": "Кредит для бизнеса оценивают по ставке, сроку и обеспечению.",
                "natural": "как получить кредит для бизнеса",
                "paraphrase": "как взять заём на развитие компании",
            },
            {
                "id": "fd3",
                "title": "Грант на развитие",
                "body": "Грант на развитие предполагает отчётность и целевое расходование.",
                "natural": "как получить грант на развитие",
                "paraphrase": "как оформить субсидию на проект",
            },
        ],
    },
    {
        "id": "strategy",
        "name": "Стратегия",
        "tags": ["стратегия", "конкуренты", "рынок", "масштабирование"],
        "concepts": [
            {
                "id": "st1",
                "title": "Конкурентный анализ",
                "body": "Конкурентный анализ сравнивает предложение, цену и каналы соперников.",
                "natural": "как провести конкурентный анализ",
                "paraphrase": "как изучить соперников на рынке",
            },
            {
                "id": "st2",
                "title": "Выход на новый рынок",
                "body": "Выход на новый рынок требует проверки спроса и каналов сбыта.",
                "natural": "как выйти на новый рынок",
                "paraphrase": "как начать работать в другом регионе",
            },
            {
                "id": "st3",
                "title": "Масштабирование бизнеса",
                "body": "Масштабирование бизнеса опирается на повторяемую экономику и процессы.",
                "natural": "как масштабировать бизнес",
                "paraphrase": "как расти без потери качества",
            },
        ],
    },
    {
        "id": "brand",
        "name": "Бренд",
        "tags": ["бренд", "стиль", "отзывы", "репутация"],
        "concepts": [
            {
                "id": "br1",
                "title": "Позиционирование бренда",
                "body": "Позиционирование бренда отвечает, чем компания отличается от других.",
                "natural": "как определить позиционирование бренда",
                "paraphrase": "чем отличаться от конкурентов в глазах клиентов",
            },
            {
                "id": "br2",
                "title": "Фирменный стиль",
                "body": "Фирменный стиль объединяет логотип, цвета и типографику.",
                "natural": "как разработать фирменный стиль",
                "paraphrase": "как сделать визуальный образ компании",
            },
            {
                "id": "br3",
                "title": "Отзывы клиентов",
                "body": "Отзывы клиентов влияют на решение о покупке сильнее рекламы.",
                "natural": "как собирать отзывы клиентов",
                "paraphrase": "как работать с мнениями покупателей",
            },
        ],
    },
]

ASPECTS: list[tuple[str, str]] = [
    (
        "для интернет-магазина",
        "В интернет-магазине решение проверяют по данным о заказах, возвратах и среднем чеке.",
    ),
    (
        "для небольшого кафе",
        "В небольшом кафе те же шаги делают вручную и сверяют с ежедневной выручкой.",
    ),
    (
        "для онлайн-школы",
        "В онлайн-школе метрики считают по группам учеников и длительности подписки.",
    ),
    (
        "для оптовой компании",
        "В оптовой компании учитывают отсрочку платежа и объём одной поставки.",
    ),
]

FORMATS = ["course", "article", "document", "webinar", "podcast", "glossary", "calculator"]
DURATIONS = [15, 30, 45, 60, 90, 120, 180]

OFF_TOPIC_QUERIES: list[str] = [
    "посадка лунохода на лунный грунт",
    "синтез химического элемента в лаборатории",
    "рецепт борща со сметаной",
    "прогноз погоды на завтра",
    "как настроить видеокарту для игр",
    "почему болит голова утром",
    "как выучить китайский язык",
    "ремонт стиральной машины своими руками",
    "схема метро москвы",
    "как играть в шахматы",
    "разведение аквариумных рыбок",
    "как выбрать горный велосипед",
]


def _is_holdout(case_id: str) -> bool:
    digest = hashlib.sha256(f"{HOLDOUT_SALT}:{case_id}".encode("utf-8")).hexdigest()
    return int(digest, 16) % HOLDOUT_MODULUS in HOLDOUT_RESIDUES


def _topic_index(topic_id: str) -> int:
    return [topic["id"] for topic in TOPICS].index(topic_id)


def _concept_tag(title: str) -> str:
    """First meaningful lowercase word of a concept title, used as a catalog tag."""
    for word in title.lower().replace(":", " ").split():
        if word not in {"и", "для", "с", "на", "в", "по"}:
            return word.strip(",")
    return title.lower()


def build_catalog() -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    materials: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []
    index = 0
    for topic in TOPICS:
        for concept in topic["concepts"]:
            for aspect_index, (aspect_name, aspect_body) in enumerate(ASPECTS):
                key = f"{topic['id']}-{concept['id']}-a{aspect_index}"
                item_type = FORMATS[index % len(FORMATS)]
                duration = DURATIONS[index % len(DURATIONS)]
                paid = index % 4 == 3
                title = f"{concept['title']} {aspect_name}"
                concept_tag = _concept_tag(concept["title"])
                materials.append({
                    "material_key": key,
                    "title": title,
                    "item_type": item_type,
                    "url": f"https://example.test/alfa-kurs/{key}",
                    "topics": [topic["name"]],
                    "tags": list(topic["tags"]) + [concept_tag],
                    "access_type": "По подписке" if paid else "Открытый",
                    "listed_price": 3900 + index % 4 * 1000 if paid else None,
                    "duration_minutes": duration,
                    "is_discoverable": True,
                    "url_state": "reachable",
                })
                chunks.append({
                    "chunk_id": f"{key}-meta",
                    "material_key": key,
                    "text": f"{title}. Тема: {topic['name']}. Теги: {', '.join(topic['tags'])}.",
                    "source_block_ids": [f"{key}-meta"],
                    "content_kind": "metadata",
                })
                if not paid:
                    chunks.append({
                        "chunk_id": f"{key}-body",
                        "material_key": key,
                        "text": f"{concept['body']} {aspect_body}",
                        "source_block_ids": [f"{key}-body"],
                        "content_kind": "body",
                    })
                index += 1
    summary = {
        "materials": len(materials),
        "chunks": len(chunks),
        "topics": len(TOPICS),
        "concepts": sum(len(topic["concepts"]) for topic in TOPICS),
        "paid_materials": sum(1 for row in materials if row["access_type"] != "Открытый"),
    }
    return materials, chunks, summary


def build_queries(materials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Relevance cases plus off-topic and filter cases.

    ``grades`` is the full judgment dictionary over every material, so no
    unjudged key can ever appear in a top-10.
    """
    cases: list[dict[str, Any]] = []
    counter = 0
    all_keys = [row["material_key"] for row in materials]

    for topic in TOPICS:
        topic_keys = [
            row["material_key"] for row in materials
            if topic["name"] in row["topics"]
        ]
        for concept_index, concept in enumerate(topic["concepts"]):
            # Rotate the aspect so it discriminates between materials instead of
            # being a constant phrase shared by every query.
            aspect_index = (concept_index + _topic_index(topic["id"])) % len(ASPECTS)
            target = f"{topic['id']}-{concept['id']}-a{aspect_index}"
            for kind, text in (("natural", concept["natural"]), ("paraphrase", concept["paraphrase"])):
                counter += 1
                case_id = f"rel{counter:03d}"
                # Closed-world judgment: every material is graded, nothing is unjudged.
                grades = {key: 0 for key in all_keys}
                for key in topic_keys:
                    grades[key] = 1
                grades[target] = 2
                cases.append({
                    "case_id": case_id,
                    "split": "holdout" if _is_holdout(case_id) else "dev",
                    "family": kind,
                    "intent": "relevance",
                    "task": f"{text} {ASPECTS[aspect_index][0]}",
                    "target": target,
                    "topics": topic_keys,
                    "grades": grades,
                })

    for number, text in enumerate(OFF_TOPIC_QUERIES):
        counter += 1
        case_id = f"ood{number:02d}"
        cases.append({
            "case_id": case_id,
            "split": "holdout" if _is_holdout(case_id) else "dev",
            "family": "off_topic",
            "intent": "refusal",
            "task": text,
            "target": None,
            "topics": [],
            "grades": {row["material_key"]: 0 for row in materials},
        })

    filter_cases = _build_filter_cases(materials)
    for offset, case in enumerate(filter_cases):
        counter += 1
        case_id = f"flt{offset:02d}"
        case.update({"case_id": case_id, "split": "holdout" if _is_holdout(case_id) else "dev"})
        cases.append(case)

    return cases


def _build_filter_cases(materials: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cases where the obvious answer must be filtered out by a constraint."""
    cases: list[dict[str, Any]] = []

    paid = [row for row in materials if row["access_type"] != "Открытый"]
    free = [row for row in materials if row["access_type"] == "Открытый"]
    long_ones = sorted(materials, key=lambda row: -row["duration_minutes"])[:8]
    podcasts = [row for row in materials if row["item_type"] == "podcast"]

    def add(target: dict[str, Any], task: str, constraints: dict[str, Any], family: str) -> None:
        topic_keys = [
            row["material_key"] for row in materials if row["topics"][0] in target["topics"]
        ]
        grades = {row["material_key"]: 0 for row in materials}
        for row in materials:
            if row["topics"][0] in target["topics"]:
                grades[row["material_key"]] = 1
        grades[target["material_key"]] = 2
        case: dict[str, Any] = {
            "family": family,
            "intent": "constraint",
            "task": task,
            "target": target["material_key"],
            "topics": topic_keys,
            "grades": grades,
        }
        # Constraint keys live at the top level because ``context_for_case``
        # reads them there.
        case.update(constraints)
        cases.append(case)

    for row in paid[:2]:
        add(row, row["title"].lower(), {"budget_preference": "free_only"}, "constraint_budget")
    for row in long_ones[:2]:
        add(row, row["title"].lower(), {"available_time_minutes": 30}, "constraint_time")
    for row in podcasts[:2]:
        add(row, row["title"].lower(), {"formats": ["course"]}, "constraint_format")
    for row in free[:2]:
        add(row, row["title"].lower(), {"formats": ["article"]}, "constraint_format")
    return cases


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    catalog_path = args.output_dir / "catalog.json"
    queries_path = args.output_dir / "queries.json"
    manifest_path = args.output_dir / "manifest.json"
    if catalog_path.exists() and queries_path.exists() and not args.force:
        print(f"Benchmark already exists in {args.output_dir} (use --force to rewrite)")
        return

    materials, chunks, summary = build_catalog()
    cases = build_queries(materials)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    catalog = {
        "version": BENCHMARK_VERSION,
        "note": "Fully synthetic Russian business catalog. No organizer or user data.",
        "materials": materials,
        "chunks": chunks,
    }
    queries = {
        "version": BENCHMARK_VERSION,
        "note": (
            "Relevance is construction-derived: target=2, same topic=1, other=0. "
            "Not human judgments."
        ),
        "holdout_salt": HOLDOUT_SALT,
        "holdout_residues": list(HOLDOUT_RESIDUES),
        "holdout_modulus": HOLDOUT_MODULUS,
        "cases": cases,
    }
    _write_json(catalog_path, catalog)
    _write_json(queries_path, queries)

    holdout_ids = sorted(case["case_id"] for case in cases if case["split"] == "holdout")
    count = lambda predicate: sum(1 for case in cases if predicate(case))  # noqa: E731
    manifest = {
        "version": BENCHMARK_VERSION,
        "summary": summary,
        "cases": len(cases),
        "cases_by_intent": {
            "relevance": count(lambda case: case["intent"] == "relevance"),
            "refusal": count(lambda case: case["intent"] == "refusal"),
            "constraint": count(lambda case: case["intent"] == "constraint"),
        },
        "cases_by_split": {
            split: count(lambda case: case["split"] == split) for split in ("dev", "holdout")
        },
        "holdout_case_ids": holdout_ids,
        "holdout_hash": hashlib.sha256("\n".join(holdout_ids).encode("utf-8")).hexdigest(),
        "files": {
            "catalog.json": hashlib.sha256(catalog_path.read_bytes()).hexdigest(),
            "queries.json": hashlib.sha256(queries_path.read_bytes()).hexdigest(),
        },
    }
    _write_json(manifest_path, manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main()
