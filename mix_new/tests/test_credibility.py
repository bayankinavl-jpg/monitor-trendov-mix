from datetime import date

from models import Credibility
from pipeline.credibility import assess_credibility

REQ = ("123", date(2026, 1, 1))


def test_official_with_requisites_is_high():
    level, _ = assess_credibility(["official_publication"], *REQ, 1)
    assert level == Credibility.HIGH


def test_official_with_publication_stage_is_high():
    level, _ = assess_credibility(["official_publication"], None, None, 1, stage="опубликован")
    assert level == Credibility.HIGH


def test_official_plain_note_is_medium():
    # Случай из первого прогона: заметка Парламентской газеты без реквизитов.
    level, _ = assess_credibility(["official_publication"], None, None, 1)
    assert level == Credibility.MEDIUM


def test_legal_with_requisites_is_high():
    level, _ = assess_credibility(["legal"], *REQ, 1)
    assert level == Credibility.HIGH


def test_legal_without_requisites_is_medium():
    level, _ = assess_credibility(["legal"], None, None, 1)
    assert level == Credibility.MEDIUM


def test_requisites_and_two_sources_is_medium():
    level, _ = assess_credibility(["general", "general"], *REQ, 2)
    assert level == Credibility.MEDIUM


def test_known_act_and_two_sources_is_medium():
    level, _ = assess_credibility(["general"], None, None, 2, referenced_acts=["Налоговый кодекс"])
    assert level == Credibility.MEDIUM


def test_single_general_source_is_low_even_with_requisites():
    level, _ = assess_credibility(["general"], *REQ, 1)
    assert level == Credibility.LOW


def test_reasons_list_signals():
    _, reasons = assess_credibility(
        ["official_publication"], *REQ, 2, stage="опубликован", referenced_acts=["381-ФЗ"]
    )
    text = " | ".join(reasons)
    assert "официальное издание" in text
    assert "№ 123 от 01.01.2026" in text
    assert "стадия документа: опубликован" in text
    assert "независимых СМИ: 2" in text
    assert "упомянут известный акт: 381-ФЗ" in text
