from models import AmendmentType, Level
from pipeline.classify import classify_amendment_type, classify_level_and_kind, is_cross_cutting, link_okved
from sources.base import CandidateAct


def _candidate(**overrides) -> CandidateAct:
    base = dict(
        raw_title="Приказ об изменении перечня товаров",
        raw_number="123",
        raw_act_kind=None,
        raw_issuing_body="Минпромторг России",
        raw_adoption_date="01.03.2026",
        raw_publication_date="05.03.2026",
        source_url="https://example.gov.ru/doc/123",
        raw_text_excerpt=None,
    )
    base.update(overrides)
    return CandidateAct(**base)


def test_link_okved_by_tnved_code():
    c = _candidate(raw_text_excerpt="Код ТН ВЭД 7208 10 000 исключён из перечня")
    codes, groups, note = link_okved(c)
    assert "24.10" in codes
    assert note is None


def test_link_okved_by_keyword_fallback():
    c = _candidate(raw_title="О пищевой продукции", raw_text_excerpt="пищевая продукция для торговли")
    codes, groups, note = link_okved(c)
    assert "продукты питания" in groups
    assert note is None


def test_link_okved_undetermined():
    c = _candidate(raw_title="Абстрактный приказ без привязки", raw_text_excerpt="")
    codes, groups, note = link_okved(c)
    assert codes == []
    assert groups == []
    assert note == "привязка не определена"


def test_cross_cutting_detected():
    c = _candidate(raw_text_excerpt="Правила распространяются на всех работодателей")
    assert is_cross_cutting(c) is True


def test_cross_cutting_not_detected():
    c = _candidate(raw_text_excerpt="Правила для производителей стройматериалов")
    assert is_cross_cutting(c) is False


def test_amendment_type_rate_change():
    c = _candidate(raw_title="Об изменении ставки акциза")
    assert classify_amendment_type(c, None) == AmendmentType.RATE_CHANGE


def test_amendment_type_new_act_by_default():
    c = _candidate(raw_title="Об утверждении нового порядка")
    assert classify_amendment_type(c, None) == AmendmentType.NEW_ACT


def test_level_and_kind_for_eaeu():
    c = _candidate(raw_issuing_body="Евразийская экономическая комиссия")
    level, kind = classify_level_and_kind(c)
    assert level == Level.EAEU


def test_level_and_kind_for_department():
    c = _candidate(raw_issuing_body="Минпромторг России")
    level, kind = classify_level_and_kind(c)
    assert level == Level.DEPT_ORDER
