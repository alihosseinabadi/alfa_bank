from app.ml.evidence import lexical_excerpt

def test_excerpt_locates_normalized_matches_after_first_page():
    assert "Ёлка" in lexical_excerpt("текст "*150+"Ёлка", ["елка"])
    assert "1C" in lexical_excerpt("текст "*150+"1C", ["1с"])
    assert "1С" in lexical_excerpt("текст "*150+"1С", ["1с"])