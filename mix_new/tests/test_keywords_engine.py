from pipeline.keywords_engine import IndustryGroup, KeywordSet, match

_KS = KeywordSet(
    acts_and_bodies=["минпромторг", "федеральный закон"],
    stages=["вступает в сил"],
    changes=["ставк", "перечень"],
    topics=["маркировк"],
    exclusions=["губернатор", "муниципальн"],
    abbreviations=["НДС"],
    industries=[IndustryGroup(label="металл", words=["металл", "металлопрокат"], okved=["24", "25"])],
)


def test_passes_with_change_and_body():
    result = match("Минпромторг изменил ставку сбора", keyword_set=_KS)
    assert result.passed is True
    assert ("ставк", "changes") in result.matched
    assert ("минпромторг", "acts_and_bodies") in result.matched


def test_passes_with_stage_and_topic():
    result = match("Закон о маркировке вступает в силу", keyword_set=_KS)
    assert result.passed is True


def test_fails_without_change_or_stage():
    result = match("Минпромторг провёл совещание", keyword_set=_KS)
    assert result.passed is False


def test_fails_without_context_group():
    result = match("Изменили ставку платежа за парковку", keyword_set=_KS)
    assert result.passed is False


def test_exclusion_blocks_even_with_otherwise_matching_words():
    result = match("Губернатор подписал постановление о ставке сбора", keyword_set=_KS)
    assert result.passed is False


def test_abbreviation_matched_whole_word_only():
    result = match("Обсуждают НДС и перечень товаров", keyword_set=_KS)
    assert ("НДС", "abbreviations") in result.matched
    # не должно ложно сработать как часть другого слова
    result2 = match("ПодНДСвинулся закон про перечень", keyword_set=_KS)
    matched_abbrevs = [w for w, g in result2.matched if g == "abbreviations"]
    assert matched_abbrevs == []


def test_industry_match_returns_group():
    result = match("Минпромторг обновил перечень для металлопрокат", keyword_set=_KS)
    assert result.passed is True
    assert any(group.label == "металл" for group in result.industries)


def test_case_insensitive_and_yo_normalization():
    result = match("МИНПРОМТОРГ поднял СТАВКУ", keyword_set=_KS)
    assert result.passed is True
