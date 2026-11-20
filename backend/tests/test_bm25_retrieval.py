"""BM25 shares access filtering and deterministic material-level results."""
import pytest
from app.ml.bm25_retriever import BM25Retriever
from test_retrieval_stage5 import material, chunk, context


def test_bm25_ranks_and_respects_filters():
    a = material("a")
    b = material("b").model_copy(update={"access_type": "По подписке"})
    index = BM25Retriever().fit([a, b], [chunk("a", "a1", "НДС налог"), chunk("b", "b1", "НДС НДС налог")])
    assert {x[0] for x in index.query(context())} == {"a", "b"}
    assert [x[0] for x in index.query(context(budget_preference="free_only"))] == ["a"]
    assert index.query(context("отсутствующийтермин")) == []


def test_bm25_pools_unique_materials_and_refit():
    a, b = material("a"), material("b")
    rows = [chunk("a", "a1", "налог ндс"), chunk("a", "a2", "ндс налог"), chunk("b", "b1", "ндс налог")]
    index = BM25Retriever().fit([a, b], rows)
    first = [(key, score, row.chunk_id) for key, score, row in index.query(context())]
    assert [x[0] for x in first] == ["a", "b"]
    index.fit([a, b], rows)
    assert first == [(key, score, row.chunk_id) for key, score, row in index.query(context())]
    for k in (0, True, -1):
        with pytest.raises(ValueError):
            index.query(context(), k)


def test_bm25_rejects_paid_body():
    paid = material().model_copy(update={"access_type": "По подписке"})
    with pytest.raises(ValueError, match="Paid body"):
        BM25Retriever().fit([paid], [chunk(content_kind="body")])
def test_bm25_rejects_incompatible_context():
    idx = BM25Retriever().fit([material()], [chunk()])
    with pytest.raises(ValueError, match="context"):
        idx.query(context().model_copy(update={"schema_version":"incompatible"}))
def test_rejects_nonfinite_parameters():
    with pytest.raises(ValueError): BM25Retriever(k1=float("nan"))
    with pytest.raises(ValueError): BM25Retriever(b=float("inf"))
def test_bm25_rejects_insufficient_lexical_coverage():
    idx=BM25Retriever().fit([material()], [chunk(text="НДС налог")])
    assert idx.query(context("НДС несуществующее1 несуществующее2 несуществующее3")) == []
    assert idx.query(context("НДС"))
def test_bm25_rejects_weak_match_despite_full_corpus_coverage():
    materials=[material(str(i)) for i in range(4)]
    words=["ндс","кадры","кредит","логистика"]
    idx=BM25Retriever().fit(materials,[chunk(str(i),str(i),word) for i,word in enumerate(words)])
    assert idx.query(context("ндс кадры кредит логистика")) == []
def test_stem_bm25_matches_russian_inflection_and_preserves_evidence():
    from app.ml.bm25_ru_stem import RussianStemBM25Retriever
    from test_bm25_retrieval import material, chunk, context
    m=material(); c=chunk(text='Клиентскому менеджеру следует заботиться о покупателях')
    model=RussianStemBM25Retriever(min_query_coverage=.3).fit([m],[c])
    found=model.query(context('клиентский покупатель'))
    assert found and found[0][2].text==c.text

def test_stem_bm25_rejects_unknown_and_preserves_numeric_tokens():
    from app.ml.bm25_ru_stem import RussianStemBM25Retriever, stem_tokens
    from test_bm25_retrieval import material, chunk, context
    model=RussianStemBM25Retriever().fit([material()],[chunk(text='НДС и 1С для магазина')])
    assert '1с' in stem_tokens('1C')
    assert not model.query(context('выращивание марсианских пальм'))


# --- Natural customer wording -------------------------------------------------
# These are the phrasings the demo receives from people who have never seen the
# catalogue.  They must resolve through morphology, synonyms and the business
# thesaurus instead of exact keyword overlap.

CATALOGUE = {
    "clients": "Первые клиенты: как найти покупателей, каналы привлечения и стабильный поток заявок.",
    "hiring": "Наём первых сотрудников: как нанять, адаптировать и распределить роли в команде.",
    "unit": "Юнит-экономика: CAC, LTV, маржа и окупаемость привлечения клиента.",
    "cash": "Управление денежным потоком: кассовый разрыв, ликвидность и платёжный календарь.",
    "tax": "Налоги бизнеса: НДС, НДФЛ и налоговые режимы для ИП и ООО.",
    "sales": "Личные продажи в розничном магазине: воронка, работа с возражениями и закрытие сделки.",
    "retail": "Продажи в магазине одежды: трафик, конверсия и поток покупателей.",
    "product": "Запуск продукта: гипотезы, MVP, проверка спроса и первые продажи.",
}


def catalogue_index():
    materials = [material(key) for key in CATALOGUE]
    rows = [chunk(key, key, text) for key, text in CATALOGUE.items()]
    return BM25Retriever(min_query_coverage=0.3).fit(materials, rows)


@pytest.mark.parametrize("question,expected", [
    ("Хочу стабильный поток клиентов", "clients"),
    ("Как нанять первого сотрудника?", "hiring"),
    ("Нужен сотрудник, не понимаю, с чего начать", "hiring"),
    ("Как посчитать юнит-экономику?", "unit"),
    ("Хочу посчитать CAC и LTV", "unit"),
    ("У меня магазин одежды, падают продажи", "retail"),
    ("Нужны деньги на развитие", "cash"),
    ("Помогите с налогами и НДС", "tax"),
    ("С чего начать запуск продукта?", "product"),
])
def test_bm25_understands_natural_business_questions(question, expected):
    found = catalogue_index().query(context(question))
    assert found, question
    assert found[0][0] == expected, (question, [item[0] for item in found])


def test_bm25_uses_synonyms_when_wording_differs():
    index = catalogue_index()
    # "нанять" is a synonym of the catalogue's "наём"; no exact token overlap.
    found = index.query(context("хочу кого-то нанять"))
    assert found and found[0][0] == "hiring"
    # "заявки" maps to the client concept even though the document says "клиенты".
    found = index.query(context("получать больше заявок"))
    assert found and found[0][0] == "clients"


def test_bm25_still_rejects_a_question_without_business_terms():
    assert catalogue_index().query(context("абракадабра про марсианские корабли")) == []


def test_analyzer_expands_inflections_and_synonyms():
    from app.ml.ru_text import analyze_text
    assert "найм" in analyze_text("наём")
    assert "клиент" in analyze_text("заявки")
    assert "финанс" in analyze_text("деньги")


def test_bm25_reads_client_flow_as_a_phrase_not_cash_flow():
    clients, cash = material("clients"), material("cash")
    rows = [
        chunk("clients", "c1", "Первые клиенты и стабильный поток заявок: каналы привлечения."),
        chunk("cash", "c2", "Управление денежным потоком: кассовый разрыв и ликвидность."),
    ]
    index = BM25Retriever().fit([clients, cash], rows)
    found = index.query(context("Хочу стабильный поток клиентов"))
    assert found and found[0][0] == "clients", [item[0] for item in found]
