from datetime import date

from models import Credibility
from pipeline.credibility import assess_credibility


def test_official_publication_is_always_high():
    result = assess_credibility(["official_publication"], None, None, 1)
    assert result == Credibility.HIGH


def test_legal_with_requisites_is_high():
    result = assess_credibility(["legal"], "123", date(2026, 1, 1), 1)
    assert result == Credibility.HIGH


def test_legal_without_requisites_is_not_high():
    result = assess_credibility(["legal"], None, None, 1)
    assert result != Credibility.HIGH


def test_requisites_and_two_sources_is_medium():
    result = assess_credibility(["general", "general"], "123", date(2026, 1, 1), 2)
    assert result == Credibility.MEDIUM


def test_single_source_without_requisites_is_low():
    result = assess_credibility(["general"], None, None, 1)
    assert result == Credibility.LOW


def test_requisites_but_single_source_is_low():
    result = assess_credibility(["general"], "123", date(2026, 1, 1), 1)
    assert result == Credibility.LOW
