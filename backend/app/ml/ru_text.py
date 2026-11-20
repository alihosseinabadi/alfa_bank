"""Russian lexical analysis for retrieval.

The catalogue is written in Russian, while users type free-form business tasks
with different word forms ("нанять" vs "найм", "клиенты" vs "клиент").  Plain
whitespace tokens therefore miss obvious matches.  This module provides the
shared analysis used by the lexical retrievers:

* NFKC / case / ``ё`` normalisation and ``1C`` -> ``1с``;
* an expanded Russian stop-word list for conversational queries;
* Snowball stemming so inflections collapse to one term;
* a small, explicit business thesaurus that adds canonical concept tokens
  ("найм", "клиент", "юнит-экономика", ...) to both documents and queries.

It is deliberately deterministic and inspectable: no hidden model, no
server-side profile data.  The same function runs at index time and query time,
so a synonym added to the thesaurus applies symmetrically.
"""
from functools import lru_cache
import re
import unicodedata

ANALYZER_VERSION = "ru-stem-syn-v2"

# Conversational filler plus the original function words.  Removing these makes
# coverage depend on the actual business terms in a question.
RU_STOP = frozenset("""
и в во на по с со для как что это или а к о об от до из за у но чтобы при ли же бы
мы вы мне нам нас вас нужен нужна нужно нужны нужного хочу хотел хотела хотим
можно нельзя пожалуйста подскажите расскажите посоветуйте помогите интересует
интересуют стоит лучше вообще сейчас уже еще есть был была были будет если когда
где кто чем чего этот эта эти того тому также очень самый более менее надо могу
сколько скольких скольким стоит стоят стоить
можете меня себя себе свой своя свои наш наша наши ваш ваша ваши их его ее они оно
она он я ты не ни да нет про над под между после перед через без ради
""".split())

# concept -> prefixes of normalised/Snowball-stemmed tokens that trigger it.
# Prefixes are matched with ``stem.startswith(prefix)``; keep them specific.
_CONCEPTS: dict[str, tuple[str, ...]] = {
    "найм": (
        "наня", "найм", "нанима", "наем", "сотрудник", "работник", "кадр", "персонал",
        "команд", "hire", "hiring", "recruit", "team",
        "зарплат", "оклад", "трудов", "отпуск", "больничн", "увольн", "ваканс",
        "резюме", "собеседован", "онбординг", "штат",
    ),
    "клиент": (
        "клиент", "покупател", "заказчик", "потребител", "лид", "заяв",
        "customer", "client", "lead",
    ),
    "маркетинг": (
        "маркет", "привлеч", "привлека", "трафик", "реклам", "продвижен",
        "канал", "outreach", "marketing", "acquisition", "advertis",
        "конкурент", "конкуренц", "аудитор", "ниш", "сегмент", "спрос", "исследова",
    ),
    "продаж": (
        "продаж", "продава", "продать", "сделк", "сбыт", "sales", "sell",
        "маркетплейс", "marketplace", "розниц", "розничн", "торгов",
        "crm", "воронк", "конверси", "ассортимент", "закупк", "поставщик", "товар",
    ),
    "финанс": (
        "финанс", "деньг", "денег", "доход", "выручк", "прибыл", "расход",
        "маржа", "маржин", "экономик", "unit", "cac", "ltv", "окупа",
        "cash", "денежн", "прибыльн", "бюджет", "затрат", "издержк", "оборот",
        "себестоим", "рентабельн", "безубыточ", "наценк", "стоимост",
        "кред", "лизинг",
    ),
    "налог": (
        "налог", "ндс", "ндфл", "налогооблож", "tax", "vat",
        "бухгалтер", "отчетн", "фактур", "фискальн", "декларац", "усн", "патент",
        "лиценз",
    ),
    "юнит-экономика": (
        "юнит", "unit-economics", "cac", "ltv", "маржин", "окупа",
        "себестоим", "рентабельн", "безубыточ", "наценк",
    ),
    "управление": (
        "управлен", "менеджмент", "процесс", "операц", "регламент", "масштаб",
        "систем", "management", "operations", "scale", "process",
        "производств", "логистик", "доставк", "аренд", "помещен", "франшиз",
        "тендер", "договор", "контрагент", "сверк", "инвентаризац", "склад", "смен",
    ),
    "запуск": (
        "запуск", "стартап", "старт", "продукт", "product", "launch", "mvp",
        "гипотез", "прототип",
    ),
    "инвестиции": (
        "инвест", "фандрайз", "fundrais", "питч", "раунд", "капитал",
        "investor", "pitch", "round", "venture", "грант", "субсид",
    ),
    "данные": (
        "данн", "аналитик", "sql", "python", "автоматизац", "таблиц", "отчет",
        "метрик", "dashboard", "analytics", "data", "excel",
    ),
    "бренд": (
        "бренд", "позиционир", "brand", "positioning",
        "товарн", "знак", "логотип", "нейминг",
    ),
    "денежный-поток": ("кассов", "разрыв", "ликвидн", "runway", "cashflow"),
}

DOMAIN_CONCEPTS = frozenset(_CONCEPTS)

# Multi-word phrases whose meaning is not the sum of their words.  "Поток
# клиентов" is customer acquisition, not cash flow; without this the word
# "поток" alone can outrank the actual client material.
_PHRASE_CONCEPTS = (
    (("поток", "клиент"), "клиент"),
    (("поток", "заяв"), "клиент"),
    (("поток", "покупател"), "клиент"),
    (("денежн", "поток"), "денежный-поток"),
    (("онлайн", "касс"), "налог"),
    (("трудов", "договор"), "найм"),
    (("оплат", "труд"), "найм"),
    (("товарн", "знак"), "бренд"),
)

# Tokens whose Snowball stem is misleading (юнит -> юн) or that are common
# business abbreviations.  Keep them exactly as written.
_PROTECTED = frozenset({"ндс", "ндфл", "cac", "ltv", "sql", "python", "1с", "ип", "юнит", "наем"})


@lru_cache(maxsize=1)
def _stemmer():
    from snowballstemmer import stemmer
    return stemmer("russian")


@lru_cache(maxsize=8192)
def _stem(token: str) -> str:
    if token in _PROTECTED or token.startswith("юнит"):
        return token
    if not any("а" <= char <= "я" for char in token):
        return token
    return _stemmer().stemWord(token)


@lru_cache(maxsize=8192)
def _concepts_for(stem: str) -> tuple[str, ...]:
    return tuple(
        concept
        for concept, prefixes in _CONCEPTS.items()
        if any(stem.startswith(prefix) for prefix in prefixes)
    )


def normalize_ru(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold().replace("ё", "е")
    text = re.sub(r"\b1c\b", "1с", text)
    return re.sub(r"\s+", " ", text).strip()


def analyze_text(text: str, *, with_concepts: bool = True) -> list[str]:
    """Return retrieval terms: stop-word filtered, stemmed, concept-expanded.

    Hyphenated terms are split so ``юнит-экономика`` contributes ``юнит`` and
    ``экономик``; both are meaningful on their own.  Numbers are preserved.
    """
    terms: list[str] = []
    stems: list[str] = []
    seen_concepts: set[str] = set()
    for token in re.findall(r"[a-zа-я0-9]+", normalize_ru(text)):
        if token in RU_STOP or len(token) < 2:
            continue
        stem = _stem(token)
        if stem in RU_STOP or len(stem) < 2:
            continue
        terms.append(stem)
        stems.append(stem)
        if with_concepts:
            for concept in _concepts_for(token) + _concepts_for(stem):
                if concept not in seen_concepts:
                    seen_concepts.add(concept)
                    terms.append(concept)
    consumed: set[str] = set()
    for (left, right), concept in _PHRASE_CONCEPTS:
        if any(a.startswith(left) and b.startswith(right) for a, b in zip(stems, stems[1:])):
            if with_concepts:
                terms.append(concept)
            # "Поток клиентов" means acquisition, not cash flow, so the
            # standalone word "поток" must not pull in finance material.
            if left == "поток" and concept == "клиент":
                consumed.add("поток")
    return [term for term in terms if term not in consumed]


def query_terms(text: str) -> set[str]:
    return set(analyze_text(text))


def has_domain_concept(terms) -> bool:
    return any(term in DOMAIN_CONCEPTS for term in terms)
