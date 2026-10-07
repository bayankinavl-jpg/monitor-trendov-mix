from mappings.okved_seed import lookup_by_code, lookup_by_keyword


def test_lookup_by_code_known_tnved():
    assert "24.10" in lookup_by_code("7208100000")


def test_lookup_by_code_unknown_returns_empty():
    assert lookup_by_code("9999999999") == []


def test_lookup_by_keyword_matches_group():
    groups, codes = lookup_by_keyword("строительные материалы для цемента")
    assert "стройматериалы" in groups


def test_lookup_by_keyword_no_match():
    groups, codes = lookup_by_keyword("произвольный текст без совпадений")
    assert groups == []
