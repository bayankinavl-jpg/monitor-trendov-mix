from datetime import date

from models import AmendmentType, Level
from pipeline.classify_news import (
    classify_amendment_type,
    classify_industry,
    classify_level,
    classify_stage,
    classify_topic,
    extract_act_requisites,
)
from pipeline.keywords_engine import IndustryGroup, KeywordSet

_KS = KeywordSet(industries=[IndustryGroup(label="металл", words=["металл", "металлопрокат"], okved=["24", "25"])])


def test_classify_amendment_type_rate_change():
    matched = [("ставка", "changes")]
    assert classify_amendment_type(matched) == AmendmentType.RATE_CHANGE


def test_classify_amendment_type_repeal_from_stage():
    matched = [("утратил силу", "stages")]
    assert classify_amendment_type(matched) == AmendmentType.REPEAL


def test_classify_amendment_type_default_new_act():
    matched = [("маркировка", "topics")]
    assert classify_amendment_type(matched) == AmendmentType.NEW_ACT


def test_classify_level_federal_law():
    matched = [("федеральный закон", "acts_and_bodies")]
    assert classify_level(matched) == Level.FEDERAL_LAW


def test_classify_level_none_when_no_match():
    assert classify_level([("ставка", "changes")]) is None


def test_classify_stage():
    matched = [("подписал закон", "stages")]
    assert classify_stage(matched) == "подписан"


def test_classify_topic_returns_first_matched():
    matched = [("маркировка", "topics")]
    assert classify_topic(matched) == "маркировка"


def test_classify_industry_returns_label_and_codes():
    matched = [("металлопрокат", "industries")]
    label, codes = classify_industry(matched, _KS)
    assert label == "металл"
    assert codes == ["24", "25"]


def test_classify_industry_empty_when_no_match():
    label, codes = classify_industry([("ставка", "changes")], _KS)
    assert label is None
    assert codes == []


def test_extract_act_requisites_number_and_date():
    number, act_date = extract_act_requisites("Приказ № 123 от 01.03.2026 внесён в реестр")
    assert number == "123"
    assert act_date == date(2026, 3, 1)


def test_extract_act_requisites_federal_law_without_number_sign():
    number, act_date = extract_act_requisites("Поправки в закон 381-ФЗ от 28 декабря 2009 г. приняты")
    assert number == "381-ФЗ"
    assert act_date == date(2009, 12, 28)


def test_extract_act_requisites_consultant_style():
    number, act_date = extract_act_requisites('Постановление Правительства РФ от 09.10.2026 N 1327 "О внесении изменений"')
    assert number == "1327"
    assert act_date == date(2026, 10, 9)


def test_extract_act_requisites_garant_style():
    number, act_date = extract_act_requisites("Приказ Минтранса России от 14 августа 2026 г. № 363")
    assert number == "363"
    assert act_date == date(2026, 8, 14)


def test_extract_act_requisites_invalid_date_ignored():
    number, act_date = extract_act_requisites("Приказ № 5 от 31.02.2026")
    assert number == "5"
    assert act_date is None


def test_extract_act_requisites_missing():
    number, act_date = extract_act_requisites("Готовится новый законопроект")
    assert number is None
    assert act_date is None
