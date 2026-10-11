from pipeline.keywords_engine import IndustryGroup, KeywordSet, match

_KS = KeywordSet(
    acts_and_bodies=["минпромторг", "федеральный закон"],
    stages=["вступает в силу", "опубликован"],
    changes=["ставка", "перечень", "запретить"],
    topics=["маркировка"],
    exclusions=["губернатор", "муниципальный"],
    abbreviations=["НДС"],
    industries=[
        IndustryGroup(label="металл", words=["металл", "металлопрокат"], okved=["24", "25"]),
        IndustryGroup(label="одежда", words=["одежда", "мех"], okved=["14"]),
        IndustryGroup(label="молочная продукция", words=["молочная продукция", "рыба"], okved=["10"]),
    ],
)


def test_passes_with_change_and_body():
    result = match("Минпромторг изменил ставку сбора", keyword_set=_KS)
    assert result.passed is True
    assert ("ставка", "changes") in result.matched
    assert ("минпромторг", "acts_and_bodies") in result.matched


def test_word_forms_match_normal_form():
    for title in ("Минпромторг поднял ставки", "Минпромторг: ставкам конец", "Ставкой займётся Минпромторг"):
        assert match(title, keyword_set=_KS).passed is True, title


def test_verb_form_matches():
    result = match("Минпромторг запретил ввоз", keyword_set=_KS)
    assert ("запретить", "changes") in result.matched


def test_phrase_matches_in_other_form():
    result = match("Закон о маркировке вступает в силу", keyword_set=_KS)
    assert result.passed is True
    assert ("вступает в силу", "stages") in result.matched


def test_fails_without_change_or_stage():
    assert match("Минпромторг провёл совещание", keyword_set=_KS).passed is False


def test_fails_without_context_group():
    assert match("Изменили ставку платежа за парковку", keyword_set=_KS).passed is False


def test_exclusion_blocks_even_with_otherwise_matching_words():
    assert match("Губернатор обсудил ставку сбора с Минпромторгом", keyword_set=_KS).passed is False


def test_part_of_name_does_not_match_industry_word():
    # Случай из первого прогона: «рыба» совпадала с частью «Рыбаря».
    result = match("Основатель «Рыбаря» рассказал о досмотре, интервью опубликовано", keyword_set=_KS)
    assert ("рыба", "industries") not in result.matched
    assert result.passed is False


def test_part_of_word_does_not_match_industry_word():
    # Случай из первого прогона: «мех» совпадал с частью «механизм».
    result = match("Власти введут ограничение и новый механизм для сайтов", keyword_set=_KS)
    assert ("мех", "industries") not in result.matched


def test_abbreviation_matched_whole_word_only():
    assert ("НДС", "abbreviations") in match("Обсуждают НДС и перечень товаров", keyword_set=_KS).matched
    matched = match("ПодНДСвинулся закон про перечень", keyword_set=_KS).matched
    assert [w for w, g in matched if g == "abbreviations"] == []


def test_industry_match_returns_group():
    result = match("Минпромторг обновил перечень для металлопроката", keyword_set=_KS)
    assert result.passed is True
    assert any(group.label == "металл" for group in result.industries)


def test_case_insensitive():
    assert match("МИНПРОМТОРГ поднял СТАВКУ", keyword_set=_KS).passed is True
